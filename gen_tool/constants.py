from __future__ import annotations

from enum import Enum


class GenType(str, Enum):
    LAY_TONG = "Lấy tổng"
    LAY_TUNG_DON = "Lấy từng đơn"
    WEB_API_CO_KIEN = "web api - có kiện"
    WEB_API_KO_KIEN = "web api - ko kiện"


GEN_TYPES_ORDER: tuple[GenType, ...] = (
    GenType.LAY_TONG,
    GenType.LAY_TUNG_DON,
    GenType.WEB_API_CO_KIEN,
    GenType.WEB_API_KO_KIEN,
)


DEFAULT_TEMPLATE_XLSX = "Điều tin - Điều nhận.xlsx"


class DispatchType(int, Enum):
    BC = 1
    WEB = 5


class GoodsType(int, Enum):
    NORMAL = 1
