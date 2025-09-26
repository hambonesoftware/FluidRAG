"""Atomic extraction stubs for requirements."""
from __future__ import annotations

import re
from typing import Dict, List

from ..validators.units import dimension_sanity, parse_units


def extract_atomic(chunk: Dict, section_hint: str | None = None) -> List[Dict]:
    text = chunk.get("text", "")
    candidates = re.split(r"(?<=[.!?])\s+", text)
    lines = [line.strip() for line in candidates if line.strip()]
    records: List[Dict] = []

    for line in lines:
        lower = line.lower()
        if not any(keyword in lower for keyword in ("shall", "must", "required", "will")):
            if not any(unit in line for unit in ("°", " psi", " mm", " in", " A", " V", " rpm", " Hz", " kW", " kVA")):
                continue

        unit_data = parse_units(line)
        record = {
            "section_id": chunk.get("section_id"),
            "section_title": section_hint,
            "text": line,
            "page": chunk.get("page"),
            "offsets": chunk.get("offsets"),
            "value": unit_data.get("value"),
            "unit": unit_data.get("unit"),
            "op": unit_data.get("op", "="),
        }
        if record.get("unit") and not dimension_sanity(record["unit"]):
            record["validator_warning"] = "dimension_unknown"
        records.append(record)

    return records


__all__ = ["extract_atomic"]
