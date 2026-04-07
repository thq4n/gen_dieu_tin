from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

import streamlit as st

from gen_tool.constants import DIEUTIN_TYPES_ORDER, DieuTinType
from gen_tool.generator import BASE_PAYLOAD, CustomerInput, GenInput, generate_payload
from gen_tool.storage import Counters, load_counters, save_counters, save_generation


@dataclass(frozen=True)
class Defaults:
    customer_id: str = "CUS-789"
    customer_name: str = "Nguyễn Văn A"
    phone: str = "0909123456"
    email: str = "nguyenvana@example.com"
    partner_id: str = "CUS01"
    partner_name: str = "Công ty TNHH TT"


def _default_counters() -> Counters:
    pickup_task_id_by_type: dict[str, str] = {}
    order_id_by_type: dict[str, str] = {}
    for t in DIEUTIN_TYPES_ORDER:
        pickup_task_id_by_type[t] = f"DTQ-{t}-0"
        order_id_by_type[t] = f"DTQ_{t}_0000"
    return Counters(pickup_task_id_by_type=pickup_task_id_by_type, order_id_by_type=order_id_by_type)


def main() -> None:
    st.set_page_config(page_title="Gen mã Điều tin/Điều nhận", layout="wide")
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
        num_orders=int(num_orders),
        has_kien=bool(has_kien),
        items_per_order=int(items_per_order),
        customer=customer,
        pickup_post_office_code=pickup_post_office_code,
        pickup_post_office_id=pickup_post_office_id,
        scheduled_pickup_date=scheduled_pickup_date,
    )

    counters = load_counters(_default_counters())
    prev_pickup_task_id = counters.pickup_task_id_by_type.get(gen_type, "")
    prev_order_id = counters.order_id_by_type.get(gen_type, "")

    st.divider()
    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Counter hiện tại")
        st.code(f"pickupTaskId seed: {prev_pickup_task_id}\norderId seed: {prev_order_id}")
        if st.button("Reset counters theo mặc định", type="secondary", use_container_width=True):
            counters = _default_counters()
            save_counters(counters)
            st.success("Đã reset counters.")
            st.rerun()

    with col2:
        st.subheader("Preview & Gen")
        if st.button("Gen và lưu", type="primary", use_container_width=True):
            result = generate_payload(
                gen_input=gen_input,
                prev_pickup_task_id=prev_pickup_task_id,
                prev_order_id=prev_order_id,
            )

            counters.pickup_task_id_by_type[gen_type] = result.pickup_task_id
            if result.last_order_id:
                counters.order_id_by_type[gen_type] = result.last_order_id
            save_counters(counters)

            out_path = save_generation(gen_type, result.pickup_task_id, result.payload)
            st.success(f"Đã lưu: {out_path.as_posix()}")
            st.json(result.payload)
        else:
            st.caption("Bấm 'Gen và lưu' để tạo file output và tăng counter.")


if __name__ == "__main__":
    main()

