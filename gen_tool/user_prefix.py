from __future__ import annotations


def operator_prefix_from_display_name(display_name: str) -> str:
    parts = [p for p in display_name.strip().split() if p]
    initials = "".join(p[0].upper() for p in parts)
    return "DT" + initials
