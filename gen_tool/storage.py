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

_COUNTERS_VERSION = 2


@dataclass(frozen=True)
class Counters:
    pickup_task_id_by_type: dict[str, str]
    order_id_by_type: dict[str, str]


def _state_path() -> Path:
    return STATE_DIR / "counters.json"


def _operator_profile_path() -> Path:
    return STATE_DIR / "operator_profile.json"


def ensure_dirs() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class OperatorProfile:
    display_name: str
    operator_prefix: str
    rabbitmq_base_url: str = ""
    rabbitmq_username: str = ""
    rabbitmq_password: str = ""
    rabbitmq_routing_key: str = "pickuptasks_queue"


def load_operator_profile() -> OperatorProfile | None:
    ensure_dirs()
    p = _operator_profile_path()
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    display = str(data.get("display_name", "")).strip()
    prefix = str(data.get("operator_prefix", "")).strip()
    if not display or not prefix:
        return None
    rk = str(data.get("rabbitmq_routing_key", "") or "pickuptasks_queue").strip()
    return OperatorProfile(
        display_name=display,
        operator_prefix=prefix,
        rabbitmq_base_url=str(data.get("rabbitmq_base_url", "")).strip().rstrip("/"),
        rabbitmq_username=str(data.get("rabbitmq_username", "")).strip(),
        rabbitmq_password=str(data.get("rabbitmq_password", "")),
        rabbitmq_routing_key=rk or "pickuptasks_queue",
    )


def save_operator_profile(profile: OperatorProfile) -> None:
    ensure_dirs()
    payload = {
        "display_name": profile.display_name.strip(),
        "operator_prefix": profile.operator_prefix.strip(),
        "rabbitmq_base_url": profile.rabbitmq_base_url.strip().rstrip("/"),
        "rabbitmq_username": profile.rabbitmq_username.strip(),
        "rabbitmq_password": profile.rabbitmq_password,
        "rabbitmq_routing_key": (profile.rabbitmq_routing_key.strip() or "pickuptasks_queue"),
    }
    _operator_profile_path().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def clear_operator_profile() -> None:
    p = _operator_profile_path()
    if p.exists():
        p.unlink()


def _migrate_legacy_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("version") == _COUNTERS_VERSION and "by_operator" in data:
        return data
    legacy_pickup = data.get("pickup_task_id_by_type") or {}
    legacy_order = data.get("order_id_by_type") or {}
    if not isinstance(legacy_pickup, dict):
        legacy_pickup = {}
    if not isinstance(legacy_order, dict):
        legacy_order = {}
    return {
        "version": _COUNTERS_VERSION,
        "by_operator": {
            "DTQ": {
                "pickup_task_id_by_type": dict(legacy_pickup),
                "order_id_by_type": dict(legacy_order),
            }
        },
    }


def _read_counters_file() -> dict[str, Any]:
    p = _state_path()
    if not p.exists():
        return {"version": _COUNTERS_VERSION, "by_operator": {}}
    raw = json.loads(p.read_text(encoding="utf-8"))
    if raw.get("version") == _COUNTERS_VERSION and isinstance(raw.get("by_operator"), dict):
        return raw
    migrated = _migrate_legacy_to_v2(raw)
    _write_counters_root(migrated)
    return migrated


def _write_counters_root(root: dict[str, Any]) -> None:
    ensure_dirs()
    _state_path().write_text(json.dumps(root, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_loaded(
    defaults: Counters,
    operator_prefix: str,
    pickup_task_seed: dict[str, Any],
    order_id_seed: dict[str, Any],
) -> Counters:
    pickup_task_id_by_type = {
        **defaults.pickup_task_id_by_type,
        **{k: v for k, v in pickup_task_seed.items() if k in defaults.pickup_task_id_by_type},
    }
    order_id_by_type = {
        **defaults.order_id_by_type,
        **{k: v for k, v in order_id_seed.items() if k in defaults.order_id_by_type},
    }

    esc = re.escape(operator_prefix)
    pickup_re = re.compile(rf"^{esc}-(?P<code>[A-Za-z0-9]+)-(?P<num>\d+)$")
    order_re = re.compile(rf"^{esc}_(?P<code>[A-Za-z0-9]+)_(?P<num>\d+)$")
    trailing_digits_re = re.compile(r"^(?P<prefix>.*?)(?P<num>\d+)$")

    for code, v in list(pickup_task_id_by_type.items()):
        m = pickup_re.match(str(v).strip())
        if m and m.group("code").upper() == str(code).upper():
            continue
        m2 = trailing_digits_re.match(str(v).strip())
        if m2:
            pickup_task_id_by_type[code] = f"{operator_prefix}-{code}-{m2.group('num')}"
        else:
            pickup_task_id_by_type[code] = defaults.pickup_task_id_by_type[code]

    for code, v in list(order_id_by_type.items()):
        m = order_re.match(str(v).strip())
        if m and m.group("code").upper() == str(code).upper():
            continue
        m2 = trailing_digits_re.match(str(v).strip())
        if m2:
            order_id_by_type[code] = f"{operator_prefix}_{code}_{m2.group('num')}"
        else:
            order_id_by_type[code] = defaults.order_id_by_type[code]

    return Counters(pickup_task_id_by_type=pickup_task_id_by_type, order_id_by_type=order_id_by_type)


def load_counters(defaults: Counters, operator_prefix: str) -> Counters:
    ensure_dirs()
    root = _read_counters_file()

    by_op = root.get("by_operator")
    if not isinstance(by_op, dict):
        by_op = {}
    op_block = by_op.get(operator_prefix)
    if not isinstance(op_block, dict):
        save_counters(defaults, operator_prefix)
        return defaults

    pickup_seed = op_block.get("pickup_task_id_by_type") or {}
    order_seed = op_block.get("order_id_by_type") or {}
    if not isinstance(pickup_seed, dict):
        pickup_seed = {}
    if not isinstance(order_seed, dict):
        order_seed = {}

    return _normalize_loaded(defaults, operator_prefix, pickup_seed, order_seed)


def save_counters(counters: Counters, operator_prefix: str) -> None:
    root = _read_counters_file()
    if "by_operator" not in root or not isinstance(root.get("by_operator"), dict):
        root["by_operator"] = {}
    root["version"] = _COUNTERS_VERSION
    by_op = root["by_operator"]
    by_op[operator_prefix] = {
        "pickup_task_id_by_type": dict(counters.pickup_task_id_by_type),
        "order_id_by_type": dict(counters.order_id_by_type),
    }
    _write_counters_root(root)


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def save_generation(dieu_tin_type: DieuTinType, pickup_task_id: str, payload: dict[str, Any]) -> Path:
    ensure_dirs()
    out_dir = OUTPUT_DIR / dieu_tin_type
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{now_stamp()}__{pickup_task_id}.txt"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
