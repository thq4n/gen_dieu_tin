from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gen_tool.constants import GenType


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
    return Counters(
        pickup_task_id_by_type=dict(data.get("pickup_task_id_by_type", defaults.pickup_task_id_by_type)),
        order_id_by_type=dict(data.get("order_id_by_type", defaults.order_id_by_type)),
    )


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


def save_generation(gen_type: GenType, pickup_task_id: str, payload: dict[str, Any]) -> Path:
    ensure_dirs()
    out_dir = OUTPUT_DIR / gen_type.name
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{now_stamp()}__{pickup_task_id}.txt"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
