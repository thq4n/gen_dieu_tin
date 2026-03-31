from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from gen_tool.constants import DEFAULT_TEMPLATE_XLSX, GEN_TYPES_ORDER, GenType
from gen_tool.excel_templates import load_templates
from gen_tool.generator import CustomerInput, GenInput, generate_payload
from gen_tool.storage import Counters, load_counters, save_counters, save_generation


@dataclass(frozen=True)
class Defaults:
    customer_id: str = "CUS-789"
    customer_name: str = "Nguyễn Văn A"
    phone: str = "0909123456"
    email: str = "nguyenvana@example.com"
    partner_id: str = "CUS01"
    partner_name: str = "Công ty TNHH TT"


def _default_counters_from_templates(templates: dict[GenType, dict]) -> Counters:
    pickup_task_id_by_type: dict[str, str] = {}
    order_id_by_type: dict[str, str] = {}
    for t in GEN_TYPES_ORDER:
        payload = templates[t]
        pickup_task_id_by_type[t.value] = str(payload.get("pickupTaskId", "")).strip() or f"{t.name}-0"
        order_id_seed = ""
        orders = payload.get("orders")
        if isinstance(orders, list) and orders and isinstance(orders[0], dict):
            order_id_seed = str(orders[0].get("orderId", "")).strip()
        order_id_by_type[t.value] = order_id_seed or f"{t.name}0000"
    return Counters(pickup_task_id_by_type=pickup_task_id_by_type, order_id_by_type=order_id_by_type)


def main() -> None:
    st.set_page_config(page_title="Gen mã Điều tin/Điều nhận", layout="wide")
    st.title("Gen mã Điều tin / Điều nhận")

    with st.sidebar:
        st.subheader("Nguồn template")
        xlsx_path = st.text_input("Excel path", value=str(Path(DEFAULT_TEMPLATE_XLSX)))
        reload_btn = st.button("Reload template", use_container_width=True)

    if "templates" not in st.session_state or reload_btn:
        st.session_state["templates"] = load_templates(xlsx_path).by_type

    templates: dict[GenType, dict] = st.session_state["templates"]

    defaults = Defaults()

    st.subheader("Chọn loại cần gen")
    gen_type = st.selectbox(
        "Loại",
        options=list(GEN_TYPES_ORDER),
        format_func=lambda x: x.value,
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
    with col_c:
        num_orders = st.number_input("Số đơn", min_value=0, max_value=500, value=1, step=1)
        items_per_order = st.number_input("Số kiện / đơn", min_value=0, max_value=500, value=1, step=1)
        st.caption("Gợi ý: 'Lấy tổng' không cần tạo orders; 'Lấy từng đơn' chỉ lấy 1 đơn.")

    customer = CustomerInput(
        sender_id=sender_id.strip(),
        sender_name=sender_name.strip(),
        sender_phone=sender_phone.strip(),
        sender_email=sender_email.strip(),
        partner_id=partner_id.strip(),
        partner_name=partner_name.strip(),
    )

    gen_input = GenInput(
        gen_type=gen_type,
        num_orders=int(num_orders),
        items_per_order=int(items_per_order),
        customer=customer,
    )

    counters = load_counters(_default_counters_from_templates(templates))
    prev_pickup_task_id = counters.pickup_task_id_by_type.get(gen_type.value, "")
    prev_order_id = counters.order_id_by_type.get(gen_type.value, "")

    st.divider()
    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Counter hiện tại")
        st.code(f"pickupTaskId seed: {prev_pickup_task_id}\norderId seed: {prev_order_id}")
        if st.button("Reset counters theo template", type="secondary", use_container_width=True):
            counters = _default_counters_from_templates(templates)
            save_counters(counters)
            st.success("Đã reset counters.")
            st.rerun()

    with col2:
        st.subheader("Preview & Gen")
        if st.button("Gen và lưu", type="primary", use_container_width=True):
            tpl = templates[gen_type]
            result = generate_payload(
                template_payload=tpl,
                gen_input=gen_input,
                prev_pickup_task_id=prev_pickup_task_id,
                prev_order_id=prev_order_id,
            )

            counters.pickup_task_id_by_type[gen_type.value] = result.pickup_task_id
            if result.last_order_id:
                counters.order_id_by_type[gen_type.value] = result.last_order_id
            save_counters(counters)

            out_path = save_generation(gen_type, result.pickup_task_id, result.payload)
            st.success(f"Đã lưu: {out_path.as_posix()}")
            st.json(result.payload)
        else:
            st.caption("Bấm 'Gen và lưu' để tạo file output và tăng counter.")


if __name__ == "__main__":
    main()

