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

_STANDARD_TOKENS = (
    "ISO",
    "IEC",
    "UL",
    "NFPA",
    "ASTM",
    "AWS",
    "NEMA",
    "IP",
    "SCCR",
)

_UNIT_PATTERN = re.compile(
    r"\b(mm|cm|m|in|ft|kg|g|lbs?|n·?m|kN|N|Hz|VAC|VDC|V|A|kA|ms|s|°C|°F|%|GB|MB|kAIC)\b",
    re.IGNORECASE,
)


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


def contains_standard(text: str) -> bool:
    tokens = (text or "").upper().split()
    return any(tok in tokens for tok in _STANDARD_TOKENS)


def contains_unit(text: str) -> bool:
    return bool(_UNIT_PATTERN.search(text or ""))
