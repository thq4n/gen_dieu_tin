from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

import streamlit as st
import streamlit.components.v1 as components
from streamlit.errors import StreamlitSecretNotFoundError

from gen_tool.constants import DIEUTIN_TYPES_ORDER, DieuTinType
from gen_tool.generator import BASE_PAYLOAD, CustomerInput, GenInput, generate_payload
from gen_tool.rabbitmq_publish import publish_amq_default, publish_body_json_for_clipboard
from gen_tool.storage import (
    Counters,
    OperatorProfile,
    clear_operator_profile,
    load_counters,
    load_form_state,
    load_operator_profile,
    load_recent_post_office_codes,
    save_counters,
    save_form_state,
    save_generation,
    save_operator_profile,
    save_recent_post_office_codes,
)
from gen_tool.user_prefix import operator_prefix_from_display_name

DEFAULT_RABBITMQ_ROUTING_KEY = "pickuptasks_queue"
MAX_RECENT_POST_OFFICES = 10
POST_OFFICE_DATA_PATH = Path(__file__).resolve().parent.parent / "data-postoffice.csv"
_GATE_KEYS = ("gate_display_name", "gate_rabbit_url", "gate_rabbit_user", "gate_rabbit_pass", "gate_rabbit_rk")
_FORM_FIELDS = (
    "gen_type",
    "sender_id",
    "sender_name",
    "sender_phone",
    "sender_email",
    "partner_id",
    "partner_name",
    "pickup_post_office_code_selected",
    "pickup_time_hms",
    "custom_location",
    "pickup_longitude_input",
    "pickup_latitude_input",
    "has_don",
    "num_orders",
    "has_kien",
    "items_per_order",
    "order_length",
    "order_width",
    "order_height",
    "item_length",
    "item_width",
    "item_height",
)


def _rabbit_section_from_secrets() -> dict[str, Any]:
    try:
        block = st.secrets["rabbitmq"]
    except (FileNotFoundError, KeyError, TypeError, StreamlitSecretNotFoundError):
        return {}
    if not hasattr(block, "get"):
        return {}
    return {
        "base_url": str(block.get("base_url", "") or "").strip().rstrip("/"),
        "username": str(block.get("username", "") or "").strip(),
        "password": str(block.get("password", "") or ""),
        "routing_key": str(block.get("routing_key", "") or "").strip(),
        "verify_ssl": bool(block.get("verify_ssl", True)),
    }


def _rabbit_verify_ssl_from_secrets() -> bool:
    return _rabbit_section_from_secrets().get("verify_ssl", True)


def _render_copy_payload_button(copy_text: str, label: str) -> None:
    js_literal = json.dumps(copy_text)
    label_js = json.dumps(label)
    components.html(
        f"""<!DOCTYPE html><html><body style="margin:0;">
<button type="button" style="padding:0.4rem 0.9rem;border-radius:0.35rem;cursor:pointer;background:#ff4b4b;color:#fff;border:none;font-weight:600;font-size:14px;font-family:sans-serif;"></button>
<script>
const t = {js_literal};
const b = document.querySelector("button");
b.textContent = {label_js};
b.addEventListener("click", () => {{
  navigator.clipboard.writeText(t).then(() => {{ b.textContent = "Đã copy"; }});
}});
</script>
</body></html>""",
        height=52,
    )


def _apply_operator_session(profile: OperatorProfile) -> None:
    st.session_state["operator_display_name"] = profile.display_name
    st.session_state["operator_prefix"] = profile.operator_prefix
    st.session_state["rabbitmq_base_url"] = profile.rabbitmq_base_url
    st.session_state["rabbitmq_username"] = profile.rabbitmq_username
    st.session_state["rabbitmq_password"] = profile.rabbitmq_password
    st.session_state["rabbitmq_routing_key"] = profile.rabbitmq_routing_key
    st.session_state["auto_publish"] = bool(profile.auto_publish)


def _operator_profile_from_session() -> OperatorProfile:
    return OperatorProfile(
        display_name=str(st.session_state.get("operator_display_name", "")).strip(),
        operator_prefix=str(st.session_state.get("operator_prefix", "")).strip(),
        rabbitmq_base_url=str(st.session_state.get("rabbitmq_base_url", "")).strip().rstrip("/"),
        rabbitmq_username=str(st.session_state.get("rabbitmq_username", "")).strip(),
        rabbitmq_password=str(st.session_state.get("rabbitmq_password", "")),
        rabbitmq_routing_key=str(st.session_state.get("rabbitmq_routing_key", DEFAULT_RABBITMQ_ROUTING_KEY)).strip()
        or DEFAULT_RABBITMQ_ROUTING_KEY,
        auto_publish=bool(st.session_state.get("auto_publish", True)),
    )


@dataclass(frozen=True)
class Defaults:
    customer_id: str = "CUS-789"
    customer_name: str = "Nguyễn Văn A"
    phone: str = "0909123456"
    email: str = "nguyenvana@example.com"
    partner_id: str = "CUS01"
    partner_name: str = "Công ty TNHH TT"


@dataclass(frozen=True)
class PostOfficeOption:
    code: str
    name: str
    latitude: float | None
    longitude: float | None


@st.cache_data(show_spinner=False)
def _load_post_office_options(csv_path: str) -> list[PostOfficeOption]:
    rows: list[PostOfficeOption] = []
    p = Path(csv_path)
    if not p.exists():
        return rows

    def _parse_float(value: str | None) -> float | None:
        v = str(value or "").strip()
        if not v or v.upper() == "NULL":
            return None
        try:
            return float(v)
        except ValueError:
            return None

    with p.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = str(row.get("PostOfficeCode", "")).strip()
            name = str(row.get("PostOfficeName", "")).strip()
            if not code:
                continue
            rows.append(
                PostOfficeOption(
                    code=code,
                    name=name,
                    latitude=_parse_float(row.get("Latitude")),
                    longitude=_parse_float(row.get("Longitude")),
                )
            )
    return rows


def _default_counters(operator_prefix: str) -> Counters:
    pickup_task_id_by_type: dict[str, str] = {}
    order_id_by_type: dict[str, str] = {}
    for t in DIEUTIN_TYPES_ORDER:
        pickup_task_id_by_type[t] = f"{operator_prefix}-{t}-0"
        order_id_by_type[t] = f"{operator_prefix}_{t}_0000"
    return Counters(pickup_task_id_by_type=pickup_task_id_by_type, order_id_by_type=order_id_by_type)


def _parse_hms_or_default(hms: str | None, fallback: datetime) -> datetime:
    value = str(hms or "").strip()
    if not re.match(r"^\d{2}:\d{2}:\d{2}$", value):
        return fallback
    hh, mm, ss = [int(part) for part in value.split(":")]
    return fallback.replace(hour=hh, minute=mm, second=ss, microsecond=0)


def _today_with_same_time(dt: datetime) -> datetime:
    now = datetime.now()
    return now.replace(hour=dt.hour, minute=dt.minute, second=dt.second, microsecond=0)


def _init_form_state(operator_prefix: str, defaults: Defaults) -> None:
    if st.session_state.get("_form_state_inited") == operator_prefix:
        return
    saved = load_form_state(operator_prefix)
    now = datetime.now().replace(microsecond=0)
    form_defaults: dict[str, Any] = {
        "gen_type": DIEUTIN_TYPES_ORDER[0] if DIEUTIN_TYPES_ORDER else "",
        "sender_id": defaults.customer_id,
        "sender_name": defaults.customer_name,
        "sender_phone": defaults.phone,
        "sender_email": defaults.email,
        "partner_id": defaults.partner_id,
        "partner_name": defaults.partner_name,
        "pickup_time_hms": now.strftime("%H:%M:%S"),
        "custom_location": False,
        "pickup_longitude_input": float(BASE_PAYLOAD.get("pickupLongitude", 0.0)),
        "pickup_latitude_input": float(BASE_PAYLOAD.get("pickupLatitude", 0.0)),
        "has_don": True,
        "num_orders": 1,
        "has_kien": False,
        "items_per_order": 2,
        "order_length": float(BASE_PAYLOAD["orders"][0]["l"]),
        "order_width": float(BASE_PAYLOAD["orders"][0]["w"]),
        "order_height": float(BASE_PAYLOAD["orders"][0]["h"]),
        "item_length": float(BASE_PAYLOAD["orders"][0]["items"][0]["l"]),
        "item_width": float(BASE_PAYLOAD["orders"][0]["items"][0]["w"]),
        "item_height": float(BASE_PAYLOAD["orders"][0]["items"][0]["h"]),
    }
    for field, default_value in form_defaults.items():
        if field in st.session_state:
            continue
        saved_value = saved.get(field, default_value)
        st.session_state[field] = saved_value
    st.session_state["_form_state_inited"] = operator_prefix


def _save_form_state(operator_prefix: str) -> None:
    payload: dict[str, Any] = {}
    for field in _FORM_FIELDS:
        payload[field] = st.session_state.get(field)
    save_form_state(operator_prefix, payload)


def _restore_operator_from_disk() -> bool:
    profile = load_operator_profile()
    if profile is None:
        return False
    if operator_prefix_from_display_name(profile.display_name) != profile.operator_prefix:
        clear_operator_profile()
        return False
    if not profile.rabbitmq_base_url or not profile.rabbitmq_username or not profile.rabbitmq_password:
        return False
    _apply_operator_session(profile)
    return True


def _render_operator_gate() -> None:
    prof = load_operator_profile()
    sec_rmq = _rabbit_section_from_secrets()
    if "gate_display_name" not in st.session_state:
        st.session_state["gate_display_name"] = prof.display_name if prof else ""
    if "gate_rabbit_url" not in st.session_state:
        st.session_state["gate_rabbit_url"] = (
            (prof.rabbitmq_base_url if prof and prof.rabbitmq_base_url else "")
            or sec_rmq.get("base_url")
            or "http://192.168.1.143:15672"
        )
    if "gate_rabbit_user" not in st.session_state:
        st.session_state["gate_rabbit_user"] = (prof.rabbitmq_username if prof else "") or sec_rmq.get(
            "username", ""
        )
    if "gate_rabbit_pass" not in st.session_state:
        st.session_state["gate_rabbit_pass"] = (prof.rabbitmq_password if prof else "") or sec_rmq.get(
            "password", ""
        )
    if "gate_rabbit_rk" not in st.session_state:
        st.session_state["gate_rabbit_rk"] = (
            (prof.rabbitmq_routing_key if prof and prof.rabbitmq_routing_key else "")
            or sec_rmq.get("routing_key", "")
            or DEFAULT_RABBITMQ_ROUTING_KEY
        )

    st.subheader("Nhập tên của bạn")
    name = st.text_input("Họ và tên", key="gate_display_name", placeholder="Nguyễn Thùy Linh, Duyên Võ, Quân")
    st.subheader("RabbitMQ (Management API)")
    st.text_input("Base URL", key="gate_rabbit_url", placeholder="http://192.168.1.143:15672")
    st.text_input("Username", key="gate_rabbit_user")
    st.text_input("Password", type="password", key="gate_rabbit_pass")
    st.text_input("Routing key", key="gate_rabbit_rk")

    stripped = str(st.session_state.get("gate_display_name", "")).strip()
    if stripped:
        preview = operator_prefix_from_display_name(stripped)
        st.caption(f"Mã sinh ID: **{preview}** — DT cộng chữ cái đầu mỗi từ trong tên.")

    if st.button("Vào ứng dụng", type="primary"):
        url = str(st.session_state.get("gate_rabbit_url", "")).strip().rstrip("/")
        user = str(st.session_state.get("gate_rabbit_user", "")).strip()
        pw = str(st.session_state.get("gate_rabbit_pass", ""))
        rk = str(st.session_state.get("gate_rabbit_rk", "")).strip() or DEFAULT_RABBITMQ_ROUTING_KEY

        if not stripped:
            st.error("Vui lòng nhập tên.")
            return
        if not url:
            st.error("Vui lòng nhập RabbitMQ base URL.")
            return
        if not user or not pw:
            st.error("Vui lòng nhập username và password RabbitMQ.")
            return

        prefix = operator_prefix_from_display_name(stripped)
        profile = OperatorProfile(
            display_name=stripped,
            operator_prefix=prefix,
            rabbitmq_base_url=url,
            rabbitmq_username=user,
            rabbitmq_password=pw,
            rabbitmq_routing_key=rk,
            auto_publish=True,
        )
        save_operator_profile(profile)
        _apply_operator_session(profile)
        for k in _GATE_KEYS:
            st.session_state.pop(k, None)
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="Gen mã Điều tin/Điều nhận", layout="wide")

    if "operator_prefix" not in st.session_state:
        if not _restore_operator_from_disk():
            st.title("Gen mã Điều tin / Điều nhận")
            _render_operator_gate()
            st.stop()

    operator_prefix = str(st.session_state["operator_prefix"])

    with st.sidebar:
        display = st.session_state.get("operator_display_name", "")
        st.caption(f"Tên: {display}" if display else f"Mã: {operator_prefix}")
        st.caption(f"Mã ID: {operator_prefix}")
        rurl = st.session_state.get("rabbitmq_base_url", "")
        ruser = st.session_state.get("rabbitmq_username", "")
        if rurl:
            st.caption(f"RabbitMQ: {rurl}")
        if ruser:
            st.caption(f"RMQ user: {ruser}")
        if st.button("Đổi người / nhập lại tên"):
            clear_operator_profile()
            for k in (
                "operator_prefix",
                "operator_display_name",
                "rabbitmq_base_url",
                "rabbitmq_username",
                "rabbitmq_password",
                "rabbitmq_routing_key",
                "last_payload",
                "_form_state_inited",
                *_GATE_KEYS,
            ):
                st.session_state.pop(k, None)
            st.rerun()

    st.title("Gen mã Điều tin / Điều nhận")

    defaults = Defaults()
    _init_form_state(operator_prefix, defaults)

    st.subheader("Chọn loại cần gen")
    def _label_for_code(code: str) -> str:
        if code == "BC":
            return "Khách hàng bưu cục"
        if code in ("HT", "HHT"):
            return "Khách hàng hệ thống"
        if code == "NH":
            return "Nhận hộ"
        if code == "KL":
            return "Khách lẻ"
        if code == "WEB":
            return "Khách hàng Web/API"
        return code

    gen_type = st.selectbox(
        "Loại",
        options=DIEUTIN_TYPES_ORDER,
        format_func=_label_for_code,
        key="gen_type",
    )

    col_a, col_b, col_c = st.columns([1, 1, 1])
    with col_a:
        sender_id = st.text_input("Customer ID (auto-fill, sửa được)", key="sender_id")
        sender_name = st.text_input("Tên khách hàng", key="sender_name")
        sender_phone = st.text_input("SĐT", key="sender_phone")
    with col_b:
        sender_email = st.text_input("Email", key="sender_email")
        partner_id = st.text_input("Partner ID", key="partner_id")
        partner_name = st.text_input("Partner name", key="partner_name")

        pickup_post_office_code_default = str(BASE_PAYLOAD.get("pickupPostOfficeCode", "")).strip()
        pickup_post_office_name_default = str(BASE_PAYLOAD.get("pickupPostOfficeName", "")).strip()

        post_office_options = _load_post_office_options(str(POST_OFFICE_DATA_PATH))
        post_office_by_code = {o.code: o for o in post_office_options}
        recent_codes = [
            code for code in load_recent_post_office_codes(operator_prefix) if code in post_office_by_code
        ]
        ordered_codes = [*recent_codes, *[o.code for o in post_office_options if o.code not in recent_codes]]
        default_code = (
            pickup_post_office_code_default
            if pickup_post_office_code_default in post_office_by_code
            else (ordered_codes[0] if ordered_codes else "")
        )
        if (
            "pickup_post_office_code_selected" not in st.session_state
            or st.session_state["pickup_post_office_code_selected"] not in post_office_by_code
        ):
            st.session_state["pickup_post_office_code_selected"] = default_code
        if ordered_codes:
            selected_code = st.selectbox(
                "Bưu cục",
                options=ordered_codes,
                key="pickup_post_office_code_selected",
                format_func=lambda code: (
                    f"{code} - {post_office_by_code[code].name}"
                    if post_office_by_code.get(code) and post_office_by_code[code].name
                    else code
                ),
            )
        else:
            selected_code = ""
            st.warning(f"Không tìm thấy dữ liệu bưu cục tại {POST_OFFICE_DATA_PATH}.")
        selected_post_office = post_office_by_code.get(selected_code)
        if selected_code:
            updated_recent_codes = [selected_code, *[code for code in recent_codes if code != selected_code]][
                :MAX_RECENT_POST_OFFICES
            ]
            if updated_recent_codes != recent_codes:
                save_recent_post_office_codes(operator_prefix, updated_recent_codes)

        pickup_post_office_code = selected_post_office.code if selected_post_office else pickup_post_office_code_default
        pickup_post_office_name = (
            selected_post_office.name if selected_post_office and selected_post_office.name else pickup_post_office_name_default
        )
        st.text_input(
            "Tên bưu cục (pickupPostOfficeName)",
            value=pickup_post_office_name,
            disabled=True,
        )
        pickup_post_office_id = pickup_post_office_code

        if "scheduled_pickup_dt" not in st.session_state:
            st.session_state["scheduled_pickup_dt"] = _parse_hms_or_default(
                st.session_state.get("pickup_time_hms"),
                datetime.now(),
            )
        else:
            current_scheduled = st.session_state["scheduled_pickup_dt"]
            if isinstance(current_scheduled, datetime):
                st.session_state["scheduled_pickup_dt"] = _today_with_same_time(current_scheduled)
            else:
                st.session_state["scheduled_pickup_dt"] = _parse_hms_or_default(
                    st.session_state.get("pickup_time_hms"),
                    datetime.now(),
                )
        scheduled_seed = st.session_state["scheduled_pickup_dt"]
        scheduled_dt = st.datetime_input(
            "Ngày giờ pick-up (scheduledPickupDate)",
            value=scheduled_seed,
            key="scheduled_pickup_dt",
        )
        st.session_state["pickup_time_hms"] = scheduled_dt.strftime("%H:%M:%S")
        scheduled_dt = _parse_hms_or_default(st.session_state["pickup_time_hms"], datetime.now())

        scheduled_pickup_date = scheduled_dt.strftime("%Y-%m-%dT %H:%M:%S+07")
        auto_longitude = (
            selected_post_office.longitude
            if selected_post_office and selected_post_office.longitude is not None
            else float(BASE_PAYLOAD.get("pickupLongitude", 0.0))
        )
        auto_latitude = (
            selected_post_office.latitude
            if selected_post_office and selected_post_office.latitude is not None
            else float(BASE_PAYLOAD.get("pickupLatitude", 0.0))
        )
        if st.session_state.get("pickup_longitude_input") != auto_longitude:
            st.session_state["pickup_longitude_input"] = float(auto_longitude)
        if st.session_state.get("pickup_latitude_input") != auto_latitude:
            st.session_state["pickup_latitude_input"] = float(auto_latitude)

        custom_location = st.toggle("Custom location", key="custom_location")
        if custom_location:
            input_longitude = st.number_input(
                "Kinh độ lấy hàng (pickupLongitude)",
                key="pickup_longitude_input",
                format="%.6f",
            )
            input_latitude = st.number_input(
                "Vĩ độ lấy hàng (pickupLatitude)",
                key="pickup_latitude_input",
                format="%.6f",
            )
            pickup_longitude = float(input_longitude)
            pickup_latitude = float(input_latitude)
        else:
            pickup_longitude = 0.0
            pickup_latitude = 0.0
    with col_c:
        has_don = st.toggle("Có đơn", key="has_don")
        num_orders = 0
        has_kien = False
        items_per_order = 1

        if has_don:
            num_orders = st.number_input("Số đơn", min_value=0, max_value=500, step=1, key="num_orders")
            has_kien = st.toggle("Đơn kiện (có nhiều kiện/đơn)", key="has_kien")
            st.markdown("**Thông tin đơn**")
            order_col_l, order_col_w, order_col_h = st.columns(3)
            with order_col_l:
                order_length = st.number_input(
                    "Dài đơn (orders[].l)",
                    min_value=0.0,
                    step=1.0,
                    format="%.2f",
                    key="order_length",
                )
            with order_col_w:
                order_width = st.number_input(
                    "Rộng đơn (orders[].w)",
                    min_value=0.0,
                    step=1.0,
                    format="%.2f",
                    key="order_width",
                )
            with order_col_h:
                order_height = st.number_input(
                    "Cao đơn (orders[].h)",
                    min_value=0.0,
                    step=1.0,
                    format="%.2f",
                    key="order_height",
                )
            item_length = float(st.session_state.get("item_length", BASE_PAYLOAD["orders"][0]["items"][0]["l"]))
            item_width = float(st.session_state.get("item_width", BASE_PAYLOAD["orders"][0]["items"][0]["w"]))
            item_height = float(st.session_state.get("item_height", BASE_PAYLOAD["orders"][0]["items"][0]["h"]))
            if has_kien:
                items_per_order = st.number_input("Số kiện / đơn", min_value=1, max_value=500, step=1, key="items_per_order")
                st.markdown("**Thông tin kiện**")
                item_col_l, item_col_w, item_col_h = st.columns(3)
                with item_col_l:
                    item_length = st.number_input(
                        "Dài kiện (orders[].items[].l)",
                        min_value=0.0,
                        step=1.0,
                        format="%.2f",
                        key="item_length",
                    )
                with item_col_w:
                    item_width = st.number_input(
                        "Rộng kiện (orders[].items[].w)",
                        min_value=0.0,
                        step=1.0,
                        format="%.2f",
                        key="item_width",
                    )
                with item_col_h:
                    item_height = st.number_input(
                        "Cao kiện (orders[].items[].h)",
                        min_value=0.0,
                        step=1.0,
                        format="%.2f",
                        key="item_height",
                    )
        else:
            order_length = float(st.session_state.get("order_length", BASE_PAYLOAD["orders"][0]["l"]))
            order_width = float(st.session_state.get("order_width", BASE_PAYLOAD["orders"][0]["w"]))
            order_height = float(st.session_state.get("order_height", BASE_PAYLOAD["orders"][0]["h"]))
            item_length = float(st.session_state.get("item_length", BASE_PAYLOAD["orders"][0]["items"][0]["l"]))
            item_width = float(st.session_state.get("item_width", BASE_PAYLOAD["orders"][0]["items"][0]["w"]))
            item_height = float(st.session_state.get("item_height", BASE_PAYLOAD["orders"][0]["items"][0]["h"]))

        st.caption("Tắt 'Có đơn': không tạo orders. Bật 'Đơn kiện': nhập số kiện/đơn.")

    customer = CustomerInput(
        sender_id=sender_id.strip(),
        sender_name=sender_name.strip(),
        sender_phone=sender_phone.strip(),
        sender_email=sender_email.strip(),
        partner_id=partner_id.strip(),
        partner_name=partner_name.strip(),
    )

    gen_input = GenInput(
        dieu_tin_type=gen_type,
        operator_prefix=operator_prefix,
        num_orders=int(num_orders),
        has_kien=bool(has_kien),
        items_per_order=int(items_per_order),
        customer=customer,
        pickup_post_office_code=pickup_post_office_code,
        pickup_post_office_id=pickup_post_office_id,
        pickup_post_office_name=pickup_post_office_name,
        scheduled_pickup_date=scheduled_pickup_date,
        pickup_longitude=float(pickup_longitude),
        pickup_latitude=float(pickup_latitude),
        order_length=float(order_length),
        order_width=float(order_width),
        order_height=float(order_height),
        item_length=float(item_length),
        item_width=float(item_width),
        item_height=float(item_height),
    )
    _save_form_state(operator_prefix)

    counters = load_counters(_default_counters(operator_prefix), operator_prefix)
    prev_pickup_task_id = counters.pickup_task_id_by_type.get(gen_type, "")
    prev_order_id = counters.order_id_by_type.get(gen_type, "")

    st.divider()
    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Counter hiện tại")
        st.code(f"pickupTaskId seed: {prev_pickup_task_id}\norderId seed: {prev_order_id}")
        if st.button("Reset counters theo mặc định", type="secondary", use_container_width=True):
            counters = _default_counters(operator_prefix)
            save_counters(counters, operator_prefix)
            st.success("Đã reset counters.")
            st.rerun()

    with col2:
        st.subheader("Preview & Gen")
        st.text_input(
            "RabbitMQ routing_key (copy & publish)",
            key="rabbitmq_routing_key",
        )
        auto_publish = st.toggle("Auto publish sau khi Gen và lưu", key="auto_publish")
        existing_profile = load_operator_profile()
        if existing_profile is not None and existing_profile.auto_publish != auto_publish:
            save_operator_profile(_operator_profile_from_session())

        gen_flash = st.session_state.pop("_gen_flash_success", None)
        if gen_flash:
            st.success(gen_flash)

        has_last_payload = isinstance(st.session_state.get("last_payload"), dict)
        gen_clicked = False
        publish_clicked = False
        if has_last_payload:
            if auto_publish:
                gen_clicked = st.button("Gen và lưu", type="primary", use_container_width=True)
            else:
                c_gen, c_pub = st.columns(2, gap="small")
                with c_gen:
                    gen_clicked = st.button("Gen và lưu", type="primary", use_container_width=True)
                with c_pub:
                    publish_clicked = st.button("Publish lên RabbitMQ", use_container_width=True)
        else:
            gen_clicked = st.button("Gen và lưu", type="primary", use_container_width=True)

        if gen_clicked:
            result = generate_payload(
                gen_input=gen_input,
                prev_pickup_task_id=prev_pickup_task_id,
                prev_order_id=prev_order_id,
            )

            counters.pickup_task_id_by_type[gen_type] = result.pickup_task_id
            if result.last_order_id:
                counters.order_id_by_type[gen_type] = result.last_order_id
            save_counters(counters, operator_prefix)

            out_path = save_generation(gen_type, result.pickup_task_id, result.payload)
            st.session_state["last_payload"] = result.payload
            flash_msg = f"Đã lưu: {out_path.as_posix()}"
            if auto_publish:
                rk = str(st.session_state.get("rabbitmq_routing_key", DEFAULT_RABBITMQ_ROUTING_KEY)).strip()
                rk = rk or DEFAULT_RABBITMQ_ROUTING_KEY
                ok, msg = publish_amq_default(
                    str(st.session_state["rabbitmq_base_url"]),
                    str(st.session_state["rabbitmq_username"]),
                    str(st.session_state["rabbitmq_password"]),
                    result.payload,
                    rk,
                    verify=_rabbit_verify_ssl_from_secrets(),
                )
                if ok:
                    flash_msg = f"{flash_msg} | {msg}"
                else:
                    flash_msg = f"{flash_msg} | Auto publish lỗi: {msg}"
            st.session_state["_gen_flash_success"] = flash_msg
            st.rerun()

        if publish_clicked:
            last_pl = st.session_state.get("last_payload")
            if isinstance(last_pl, dict):
                rk = str(st.session_state.get("rabbitmq_routing_key", DEFAULT_RABBITMQ_ROUTING_KEY)).strip()
                rk = rk or DEFAULT_RABBITMQ_ROUTING_KEY
                ok, msg = publish_amq_default(
                    str(st.session_state["rabbitmq_base_url"]),
                    str(st.session_state["rabbitmq_username"]),
                    str(st.session_state["rabbitmq_password"]),
                    last_pl,
                    rk,
                    verify=_rabbit_verify_ssl_from_secrets(),
                )
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

        last_pl = st.session_state.get("last_payload")
        if isinstance(last_pl, dict):
            rk = str(st.session_state.get("rabbitmq_routing_key", DEFAULT_RABBITMQ_ROUTING_KEY)).strip()
            rk = rk or DEFAULT_RABBITMQ_ROUTING_KEY
            _render_copy_payload_button(
                publish_body_json_for_clipboard(last_pl, rk),
                "Copy body publish RabbitMQ",
            )
            st.json(last_pl)

        if not isinstance(st.session_state.get("last_payload"), dict) and not gen_clicked:
            st.caption("Bấm 'Gen và lưu' để tạo file output và tăng counter.")


if __name__ == "__main__":
    main()

