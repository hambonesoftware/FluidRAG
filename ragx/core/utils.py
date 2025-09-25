"""Shared utilities."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List


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


_KEY_VALUE_PAT = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z0-9 /%]+?)\s*[:=]\s*(?P<value>[\d.]+)\s*(?P<unit>[A-Za-z°%/0-9]+)?"
)

_NUMERIC_PAT = re.compile(r"\d+(?:[\d./\s]*\d+)?")
_UNIT_PAT = re.compile(
    r"\b(mm|in|µm|um|°c|°f|hz|k?pa|k?n|k?a|vac|vdc|v|a|ka|kAIC|ms|s|%|gb|gbps|mbps|mm²|awg|weeks|days|hours)\b",
    re.IGNORECASE,
)
_STANDARD_PAT = re.compile(
    r"\b(ISO|IEC|UL|NFPA|ASME|ASTM|AWS|ISA|API|GAMP)\s?-?\s?[0-9A-Z./-]+",
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


def extract_numbers(text: str) -> List[str]:
    return [m.group(0) for m in _NUMERIC_PAT.finditer(text or "")]


def has_unit(text: str) -> bool:
    return bool(_UNIT_PAT.search(text or ""))


def extract_standards(text: str) -> List[str]:
    return [m.group(0) for m in _STANDARD_PAT.finditer(text or "")]


def has_standard(text: str) -> bool:
    return bool(extract_standards(text))
