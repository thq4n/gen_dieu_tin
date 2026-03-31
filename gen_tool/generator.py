from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from gen_tool.constants import GenType, GoodsType
from gen_tool.id_sequence import next_order_id, next_pickup_task_id


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
    gen_type: GenType
    num_orders: int
    items_per_order: int
    customer: CustomerInput


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


def generate_payload(
    template_payload: dict[str, Any],
    gen_input: GenInput,
    prev_pickup_task_id: str,
    prev_order_id: str,
) -> GenResult:
    payload = copy.deepcopy(template_payload)

    pickup_task_id = next_pickup_task_id(prev_pickup_task_id)
    payload["pickupTaskId"] = pickup_task_id

    _set_customer_fields(payload, gen_input.customer)

    orders = _ensure_orders(payload)
    orders.clear()

    last_order_id: str | None = None
    order_id = prev_order_id

    template_order = _base_order_from_template(template_payload)

    if gen_input.gen_type == GenType.LAY_TONG:
        last_order_id = order_id
        return GenResult(pickup_task_id=pickup_task_id, last_order_id=last_order_id, payload=payload)

    for _ in range(gen_input.num_orders):
        order_id = next_order_id(order_id)
        last_order_id = order_id
        order = copy.deepcopy(template_order)
        order["orderId"] = order_id

        if gen_input.gen_type == GenType.WEB_API_CO_KIEN:
            order["items"] = _make_items(order_id, gen_input.items_per_order, template_order)
        else:
            order["items"] = []

        _normalize_goods_type_key(order)
        orders.append(order)

    if gen_input.gen_type == GenType.LAY_TUNG_DON:
        payload["orders"] = orders[:1]

    return GenResult(pickup_task_id=pickup_task_id, last_order_id=last_order_id, payload=payload)
