from __future__ import annotations

from enum import Enum

DieuTinType = str

DIEUTIN_TYPES_ORDER: tuple[str, ...] = (
    "BC",
    "HT",
    "NH",
    "KL",
    "WEB",
)


DEFAULT_TEMPLATE_XLSX = "Điều tin - Điều nhận.xlsx"


class DispatchType(int, Enum):
    POST_OFFICE = 1
    SYSTEM = 2
    PROXY_PICKUP = 3
    RETAIL = 4
    WEB_API = 5


DISPATCH_TYPE_FALLBACK_BY_DIEUTIN: dict[DieuTinType, DispatchType] = {
    "BC": DispatchType.POST_OFFICE,
    "HT": DispatchType.SYSTEM,
    "HHT": DispatchType.SYSTEM,
    "NH": DispatchType.PROXY_PICKUP,
    "KL": DispatchType.RETAIL,
    "WEB": DispatchType.WEB_API,
}


class GoodsType(int, Enum):
    NORMAL = 1
