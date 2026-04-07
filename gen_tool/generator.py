from __future__ import annotations

import copy
from dataclasses import dataclass
import re
from datetime import datetime, timezone
from typing import Any

from gen_tool.constants import DieuTinType, DISPATCH_TYPE_FALLBACK_BY_DIEUTIN, DispatchType, GoodsType
from gen_tool.id_sequence import next_pickup_task_id


@dataclass(frozen=True)
class CustomerInput:
    sender_id: str
    sender_name: str
    sender_phone: str
    sender_email: str
    partner_id: str
    partner_name: str


@dataclass(frozen=True)
class GenInput:
    dieu_tin_type: DieuTinType
    num_orders: int
    has_kien: bool
    items_per_order: int
    customer: CustomerInput
    pickup_post_office_code: str
    pickup_post_office_id: str
    scheduled_pickup_date: str


@dataclass(frozen=True)
class GenResult:
    pickup_task_id: str
    last_order_id: str | None
    payload: dict[str, Any]


def _set_customer_fields(payload: dict[str, Any], customer: CustomerInput) -> None:
    payload["senderId"] = customer.sender_id
    payload["senderName"] = customer.sender_name
    payload["senderPhone"] = customer.sender_phone
    payload["senderEmail"] = customer.sender_email
    payload["partnerId"] = customer.partner_id
    payload["partnerName"] = customer.partner_name


def _ensure_orders(payload: dict[str, Any]) -> list[dict[str, Any]]:
    orders = payload.get("orders")
    if not isinstance(orders, list):
        orders = []
        payload["orders"] = orders
    return orders


def _normalize_goods_type_key(order: dict[str, Any]) -> None:
    if "goods_type" in order:
        if "goodsType" not in order:
            order["goodsType"] = order.pop("goods_type")
        else:
            del order["goods_type"]
    if "goodsType" not in order:
        order["goodsType"] = int(GoodsType.NORMAL)


def _base_order_from_template(template_payload: dict[str, Any]) -> dict[str, Any]:
    orders = template_payload.get("orders")
    if isinstance(orders, list) and orders:
        if isinstance(orders[0], dict):
            o = copy.deepcopy(orders[0])
            _normalize_goods_type_key(o)
            return o
    return {
        "orderId": "",
        "createdAt": template_payload.get("createdAt"),
        "weight": 1.0,
        "l": 10.0,
        "w": 5.0,
        "h": 3.0,
        "goodsType": int(GoodsType.NORMAL),
        "items": [],
    }


def _make_items(order_id: str, count: int, template_order: dict[str, Any]) -> list[dict[str, Any]]:
    item_template = None
    items = template_order.get("items")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        item_template = items[0]
    if item_template is None:
        item_template = {"orderId": order_id, "orderItemId": order_id, "weight": 0.5, "l": 5.0, "w": 2.0, "h": 1.0}

    out: list[dict[str, Any]] = []
    for i in range(1, count + 1):
        it = copy.deepcopy(item_template)
        it["orderId"] = order_id
        it["orderItemId"] = order_id if i == 1 else f"{order_id}/{i}"
        out.append(it)
    return out


_LAST_NUMBER_RE = re.compile(r"^(?P<prefix>.*?)(?P<num>\d+)$")


def _next_dtq_order_id(dieu_tin_type: DieuTinType, prev_order_id: str) -> str:
    prev = prev_order_id.strip()
    m = _LAST_NUMBER_RE.match(prev)
    if not m:
        return f"DTQ_{dieu_tin_type}_1"
    num_s = m.group("num")
    width = len(num_s)
    num = int(num_s) + 1
    return f"DTQ_{dieu_tin_type}_{num:0{width}d}"


def _now_created_at() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


BASE_PAYLOAD: dict[str, Any] = {
    "eventType": "RabbitMqPickupTaskEvent",
    "eventId": "b7c2f6a1-3a9d-4d4a-9c2f-8f3a9c2d1e55",
    "createdAt": "2026-03-10T10:10:30Z",
    "pickupTaskId": "DTQ-TYPE-0",
    "dispatchType": 2,
    "dispatchMethod": 1,
    "pickupPostOfficeCode": "TMT",
    "scheduledPickupDate": "2026-04-02T 17:15:00+07",
    "pickupPostOfficeId": "0000000b-4b33-4200-0000-000000000000",
    "pickupPostOfficeName": "SHH - Sư Vạn Hạnh",
    "pickupAddress": "92 Đường số 49, Khu phố 8, Phường Bình Tân, HỒ CHÍ MINH",
    "pickupWardId": "HCMBAN",
    "pickupWardName": "Bến Nghé",
    "pickupProvinceId": "HCM",
    "pickupProvinceName": "TP. Hồ Chí Minh",
    "pickupCountryId": "VN",
    "pickupCountryName": "Việt Nam",
    "pickupLongitude": 0,
    "pickupLatitude": 0,
    "senderId": "CUS-789",
    "senderName": "Nguyễn Văn A",
    "senderPhone": "0909123456",
    "senderEmail": "nguyenvana@example.com",
    "partnerId": "CUS01",
    "partnerName": "Công ty TNHH TT",
    "assignedEmployeeId": "",
    "assignedEmployeeName": "",
    "assignedEmployeeCode": "",
    "assignedEmployeePhone": "",
    "scheduledPickupTimeFrom": "09:32:00",
    "scheduledPickupTimeTo": "09:35:00",
    "actualPickupTime": None,
    "statusId": "waiting_for_assignment",
    "statusName": "Chờ phân công",
    "totalItems": 3,
    "totalWeight": 5.75,
    "totalCalWeight": 6.2,
    "totalCodAmount": 1500000,
    "l": 20,
    "h": 25,
    "w": 35,
    "serviceTypeId": "EXPRESS",
    "serviceTypeName": "Chuyển phát nhanh",
    "priority": 1,
    "notes": "Khách yêu cầu gọi trước khi đến",
    "internalNotes": "Ưu tiên xử lý trong buổi sáng",
    "metadataJson": "{\"source\":\"mobile_app\",\"campaign\":\"TET2026\"}",
    "createdBy": "326f6e49-6292-4ee3-9b8e-c84df103b722",
    "createdByName": "Phạm Phan Nhật Minh",
    "updatedBy": None,
    "updatedByName": None,
    "isDeleted": False,
    "isCancelled": False,
    "cancellationReason": None,
    "orders": [
        {
            "orderId": "DTQ_HT_0001",
            "createdAt": "2026-03-10T10:10:30Z",
            "weight": 1,
            "l": 10,
            "w": 5,
            "h": 3,
            "goodsType": 1,
            "items": [
                {
                    "orderId": "DTQ_HT_0001",
                    "orderItemId": "DTQ_HT_0001",
                    "weight": 0.5,
                    "l": 5,
                    "w": 2,
                    "h": 1,
                },
                {
                    "orderId": "DTQ_HT_0001",
                    "orderItemId": "DTQ_HT_0001/2",
                    "weight": 0.5,
                    "l": 5,
                    "w": 2,
                    "h": 1,
                },
            ],
        }
    ],
}


def generate_payload(
    gen_input: GenInput,
    prev_pickup_task_id: str,
    prev_order_id: str,
) -> GenResult:
    payload = copy.deepcopy(BASE_PAYLOAD)
    payload["createdAt"] = _now_created_at()
    dispatch = DISPATCH_TYPE_FALLBACK_BY_DIEUTIN.get(gen_input.dieu_tin_type)
    if dispatch is None:
        dispatch = DispatchType.WEB_API if "WEB" in gen_input.dieu_tin_type.upper() else DispatchType.POST_OFFICE
    payload["dispatchType"] = int(dispatch.value)

    payload["pickupPostOfficeCode"] = gen_input.pickup_post_office_code.strip()
    # Theo yêu cầu: pickupPostOfficeId giống pickupPostOfficeCode.
    payload["pickupPostOfficeId"] = gen_input.pickup_post_office_code.strip()
    payload["scheduledPickupDate"] = gen_input.scheduled_pickup_date.strip()

    pickup_task_id = next_pickup_task_id(prev_pickup_task_id)
    payload["pickupTaskId"] = pickup_task_id

    _set_customer_fields(payload, gen_input.customer)

    orders = _ensure_orders(payload)
    orders.clear()

    last_order_id: str | None = None
    order_id = prev_order_id

    template_order = _base_order_from_template(BASE_PAYLOAD)
    template_order["createdAt"] = payload["createdAt"]

    for _ in range(gen_input.num_orders):
        order_id = _next_dtq_order_id(gen_input.dieu_tin_type, order_id)
        last_order_id = order_id
        order = copy.deepcopy(template_order)
        order["orderId"] = order_id
        order["createdAt"] = payload["createdAt"]

        count = gen_input.items_per_order if gen_input.has_kien else 1
        order["items"] = _make_items(order_id, count, template_order)

        _normalize_goods_type_key(order)
        orders.append(order)

    return GenResult(pickup_task_id=pickup_task_id, last_order_id=last_order_id, payload=payload)
