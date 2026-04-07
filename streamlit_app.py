from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from gen_tool.constants import DIEUTIN_TYPES_ORDER, DieuTinType
from gen_tool.generator import BASE_PAYLOAD, CustomerInput, GenInput, generate_payload
from gen_tool.rabbitmq_publish import publish_amq_default, publish_body_json_for_clipboard
from gen_tool.storage import (
    Counters,
    OperatorProfile,
    clear_operator_profile,
    load_counters,
    load_operator_profile,
    save_counters,
    save_generation,
    save_operator_profile,
)
from gen_tool.user_prefix import operator_prefix_from_display_name

DEFAULT_RABBITMQ_ROUTING_KEY = "pickuptasks_queue"
_GATE_KEYS = ("gate_display_name", "gate_rabbit_url", "gate_rabbit_user", "gate_rabbit_pass", "gate_rabbit_rk")


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


@dataclass(frozen=True)
class Defaults:
    customer_id: str = "CUS-789"
    customer_name: str = "Nguyễn Văn A"
    phone: str = "0909123456"
    email: str = "nguyenvana@example.com"
    partner_id: str = "CUS01"
    partner_name: str = "Công ty TNHH TT"


def _default_counters(operator_prefix: str) -> Counters:
    pickup_task_id_by_type: dict[str, str] = {}
    order_id_by_type: dict[str, str] = {}
    for t in DIEUTIN_TYPES_ORDER:
        pickup_task_id_by_type[t] = f"{operator_prefix}-{t}-0"
        order_id_by_type[t] = f"{operator_prefix}_{t}_0000"
    return Counters(pickup_task_id_by_type=pickup_task_id_by_type, order_id_by_type=order_id_by_type)


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
    if "gate_display_name" not in st.session_state:
        st.session_state["gate_display_name"] = prof.display_name if prof else ""
    if "gate_rabbit_url" not in st.session_state:
        st.session_state["gate_rabbit_url"] = (
            prof.rabbitmq_base_url if prof and prof.rabbitmq_base_url else "http://192.168.1.143:15672"
        )
    if "gate_rabbit_user" not in st.session_state:
        st.session_state["gate_rabbit_user"] = prof.rabbitmq_username if prof else ""
    if "gate_rabbit_pass" not in st.session_state:
        st.session_state["gate_rabbit_pass"] = prof.rabbitmq_password if prof else ""
    if "gate_rabbit_rk" not in st.session_state:
        st.session_state["gate_rabbit_rk"] = (
            prof.rabbitmq_routing_key if prof and prof.rabbitmq_routing_key else DEFAULT_RABBITMQ_ROUTING_KEY
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
                *_GATE_KEYS,
            ):
                st.session_state.pop(k, None)
            st.rerun()

    st.title("Gen mã Điều tin / Điều nhận")

    defaults = Defaults()

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
    )

    col_a, col_b, col_c = st.columns([1, 1, 1])
    with col_a:
        sender_id = st.text_input("Customer ID (auto-fill, sửa được)", value=defaults.customer_id)
        sender_name = st.text_input("Tên khách hàng", value=defaults.customer_name)
        sender_phone = st.text_input("SĐT", value=defaults.phone)
    with col_b:
        sender_email = st.text_input("Email", value=defaults.email)
        partner_id = st.text_input("Partner ID", value=defaults.partner_id)
        partner_name = st.text_input("Partner name", value=defaults.partner_name)

        pickup_post_office_code_default = str(BASE_PAYLOAD.get("pickupPostOfficeCode", "")).strip()
        pickup_post_office_id_default = str(BASE_PAYLOAD.get("pickupPostOfficeId", "")).strip()
        scheduled_pickup_date_default_str = str(BASE_PAYLOAD.get("scheduledPickupDate", "")).strip()

        def _default_scheduled_pickup_datetime(s: str) -> datetime:
            """
            Mặc định là 'hôm nay'.
            Nếu template có giờ/phút/giây hợp lệ (vd: 2026-03-31T 07:00:00+07)
            thì giữ nguyên thời gian đó, chỉ thay ngày thành hôm nay.
            """
            now = datetime.now()
            m = re.match(
                r"^(?P<date>\d{4}-\d{2}-\d{2})T\s(?P<time>\d{2}:\d{2}:\d{2})(?P<offset>[+-]\d{2})$",
                s,
            )
            if not m:
                return now
            time_s = m.group("time")
            hh, mm, ss = [int(x) for x in time_s.split(":")]
            return now.replace(hour=hh, minute=mm, second=ss)

        pickup_post_office_code = st.text_input(
            "Bưu cục (pickupPostOfficeCode)",
            value=pickup_post_office_code_default,
        )
        # pickupPostOfficeId theo pickupPostOfficeCode (giống yêu cầu của bạn).
        pickup_post_office_id = pickup_post_office_code

        scheduled_dt = st.datetime_input(
            "Ngày giờ pick-up (scheduledPickupDate)",
            value=_default_scheduled_pickup_datetime(scheduled_pickup_date_default_str),
        )

        # Payload format currently uses a space after 'T': "YYYY-MM-DDT HH:MM:SS+07"
        scheduled_pickup_date = scheduled_dt.strftime("%Y-%m-%dT %H:%M:%S+07")
    with col_c:
        has_don = st.toggle("Có đơn", value=True)
        num_orders = 0
        has_kien = False
        items_per_order = 1

        if has_don:
            num_orders = st.number_input("Số đơn", min_value=0, max_value=500, value=1, step=1)
            has_kien = st.toggle("Đơn kiện (có nhiều kiện/đơn)", value=False)
            if has_kien:
                items_per_order = st.number_input("Số kiện / đơn", min_value=1, max_value=500, value=2, step=1)

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
        scheduled_pickup_date=scheduled_pickup_date,
    )

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

        gen_flash = st.session_state.pop("_gen_flash_success", None)
        if gen_flash:
            st.success(gen_flash)

        has_last_payload = isinstance(st.session_state.get("last_payload"), dict)
        gen_clicked = False
        publish_clicked = False
        if has_last_payload:
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
            st.session_state["_gen_flash_success"] = f"Đã lưu: {out_path.as_posix()}"
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

