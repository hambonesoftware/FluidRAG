"""Validator for extracted rows."""

from __future__ import annotations

from typing import Dict, List

from .utils import extract_numbers, has_standard, has_unit

ALLOWED_PASSES = {
    "Mechanical",
    "Electrical",
    "Controls",
    "Software",
    "Project Management",
}


def _has_anchor(row: Dict) -> bool:
    anchors = row.get("anchors") or []
    return bool(anchors)


def _spec_valid(text: str) -> bool:
    if not text:
        return False
    tokens = text.split()
    if len(tokens) >= 8:
        return True
    if has_standard(text):
        return True
    if has_unit(text) and extract_numbers(text):
        return True
    return False


def _merge_lists(values):
    merged = []
    seen = set()
    for value in values:
        if not value:
            continue
        if value in seen:
            continue
        merged.append(value)
        seen.add(value)
    return merged


def validate_rows(rows):
    valid: List[Dict] = []
    seen = {}
    report = {"dropped": 0}
    for row in rows:
        if row.get("pass") not in ALLOWED_PASSES:
            report["dropped"] += 1
            continue
        if not _has_anchor(row):
            report["dropped"] += 1
            continue
        spec = row.get("spec") or row.get("text") or ""
        if not _spec_valid(spec):
            report["dropped"] += 1
            continue
        key = (row.get("document_id"), spec.lower())
        if key in seen:
            prev = seen[key]
            prev["provenance"] = sorted(
                {*(prev.get("provenance") or []), *(row.get("provenance") or [])}
            )
            prev["pages"] = sorted({*(prev.get("pages") or []), *(row.get("pages") or [])})
            continue
        row.setdefault("provenance", [])
        row.setdefault("pages", [])
        row["provenance"] = _merge_lists(row["provenance"])
        row["pages"] = _merge_lists(row["pages"])
        seen[key] = row
        valid.append(row)
    return valid, report
