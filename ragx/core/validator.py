"""Validator for extracted rows."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from .utils import contains_standard, contains_unit, merge_provenance

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


_STANDALONE_STANDARD = re.compile(r"\b([A-Z]{2,}\s?\d{2,}[A-Z0-9\-]*)\b")


def _spec_valid(text: str) -> bool:
    if not text:
        return False
    tokens = text.split()
    if len(tokens) >= 8:
        return True
    if contains_standard(text) or contains_unit(text):
        return True
    if _STANDALONE_STANDARD.search(text):
        return True
    return False


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
            merged = merge_provenance(prev, row)
            prev["provenance"] = merged["provenance"]
            prev["pages"] = merged["pages"]
            continue
        seen[key] = row
        valid.append(row)
    return valid, report
