from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import json5
import openpyxl

from gen_tool.constants import DEFAULT_TEMPLATE_XLSX, GenType


@dataclass(frozen=True)
class TemplateBundle:
    by_type: dict[GenType, dict[str, Any]]


def load_templates(xlsx_path: str | Path = DEFAULT_TEMPLATE_XLSX) -> TemplateBundle:
    p = Path(xlsx_path)
    wb = openpyxl.load_workbook(p, data_only=False)

    by_type: dict[GenType, dict[str, Any]] = {}
    for gen_type in GenType:
        if gen_type.value not in wb.sheetnames:
            raise ValueError(f"Missing sheet: {gen_type.value}")
        ws = wb[gen_type.value]
        raw = ws["A1"].value
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"Sheet {gen_type.value} A1 is empty")
        by_type[gen_type] = json5.loads(raw)

    return TemplateBundle(by_type=by_type)
