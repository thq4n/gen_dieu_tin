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


class DispatchMethod(int, Enum):
    PICKUP = 1
    DELIVERY = 2

    @property
    def description(self) -> str:
        match self:
            case DispatchMethod.PICKUP:
                return "Điều nhận"
            case DispatchMethod.DELIVERY:
                return "Điều chở"
            case _:
                return str(int(self))


DISPATCH_METHODS_ORDER: tuple[DispatchMethod, ...] = (
    DispatchMethod.PICKUP,
    DispatchMethod.DELIVERY,
)


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
