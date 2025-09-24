"""Shared utilities."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple


def normalize_text(text: str) -> str:
    return (text or "").strip().lower()


def build_anchor(number: str | None, name: str) -> str:
    name = (name or "").strip()
    if number:
        return f"{number} — {name}" if name else str(number)
    return name


def merge_provenance(lhs: Dict[str, Iterable], rhs: Dict[str, Iterable]) -> Dict[str, List]:
    pages = sorted({*(lhs.get("pages") or []), *(rhs.get("pages") or [])})
    sections = sorted({*(lhs.get("provenance") or []), *(rhs.get("provenance") or [])})
    return {"pages": pages, "provenance": sections}

_KEY_VALUE_PAT = re.compile(r"(?P<name>[A-Za-z][A-Za-z0-9 /%]+?)\s*[:=]\s*(?P<value>[\d.]+)\s*(?P<unit>[A-Za-z°%/0-9]+)?")


def extract_key_values(text: str) -> List[Dict[str, str]]:
    matches = []
    for m in _KEY_VALUE_PAT.finditer(text or ""):
        matches.append(
            {
                "name": m.group("name").strip(),
                "value": m.group("value"),
                "unit": (m.group("unit") or "").strip(),
            }
        )
    return matches
