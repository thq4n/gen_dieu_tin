from __future__ import annotations

import re


_LAST_NUMBER_RE = re.compile(r"^(?P<prefix>.*?)(?P<num>\d+)$")


def next_id(prev: str, step: int = 1) -> str:
    m = _LAST_NUMBER_RE.match(prev.strip())
    if not m:
        return prev.strip() + str(step)
    prefix = m.group("prefix")
    num_s = m.group("num")
    width = len(num_s)
    num = int(num_s) + step
    return f"{prefix}{num:0{width}d}"


def next_pickup_task_id(prev: str) -> str:
    return next_id(prev, step=1)


def next_order_id(prev: str) -> str:
    return next_id(prev, step=1)
