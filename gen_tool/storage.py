from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from gen_tool.constants import DieuTinType


STATE_DIR = Path("state")
OUTPUT_DIR = Path("output")


@dataclass(frozen=True)
class Counters:
    pickup_task_id_by_type: dict[str, str]
    order_id_by_type: dict[str, str]


def _state_path() -> Path:
    return STATE_DIR / "counters.json"


def ensure_dirs() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_counters(defaults: Counters) -> Counters:
    ensure_dirs()
    p = _state_path()
    if not p.exists():
        save_counters(defaults)
        return defaults
    data = json.loads(p.read_text(encoding="utf-8"))
    pickup_task_seed = data.get("pickup_task_id_by_type", {})
    order_id_seed = data.get("order_id_by_type", {})
    # Chỉ giữ lại những key mà UI/gen đang dùng (tránh state cũ chứa key khác).
    pickup_task_id_by_type = {
        **defaults.pickup_task_id_by_type,
        **{k: v for k, v in pickup_task_seed.items() if k in defaults.pickup_task_id_by_type},
    }
    order_id_by_type = {
        **defaults.order_id_by_type,
        **{k: v for k, v in order_id_seed.items() if k in defaults.order_id_by_type},
    }

    pickup_re = re.compile(r"^DTQ-(?P<code>[A-Za-z0-9]+)-(?P<num>\d+)$")
    order_re = re.compile(r"^DTQ_(?P<code>[A-Za-z0-9]+)_(?P<num>\d+)$")
    trailing_digits_re = re.compile(r"^(?P<prefix>.*?)(?P<num>\d+)$")

    for code, v in list(pickup_task_id_by_type.items()):
        m = pickup_re.match(str(v).strip())
        if m and m.group("code").upper() == str(code).upper():
            continue
        m2 = trailing_digits_re.match(str(v).strip())
        if m2:
            pickup_task_id_by_type[code] = f"DTQ-{code}-{m2.group('num')}"
        else:
            pickup_task_id_by_type[code] = defaults.pickup_task_id_by_type[code]

    for code, v in list(order_id_by_type.items()):
        m = order_re.match(str(v).strip())
        if m and m.group("code").upper() == str(code).upper():
            continue
        m2 = trailing_digits_re.match(str(v).strip())
        if m2:
            order_id_by_type[code] = f"DTQ_{code}_{m2.group('num')}"
        else:
            order_id_by_type[code] = defaults.order_id_by_type[code]

    return Counters(pickup_task_id_by_type=pickup_task_id_by_type, order_id_by_type=order_id_by_type)


def save_counters(counters: Counters) -> None:
    ensure_dirs()
    _state_path().write_text(
        json.dumps(
            {
                "pickup_task_id_by_type": counters.pickup_task_id_by_type,
                "order_id_by_type": counters.order_id_by_type,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def save_generation(dieu_tin_type: DieuTinType, pickup_task_id: str, payload: dict[str, Any]) -> Path:
    ensure_dirs()
    out_dir = OUTPUT_DIR / dieu_tin_type
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{now_stamp()}__{pickup_task_id}.txt"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
