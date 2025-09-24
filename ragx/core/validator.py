"""Validator for extracted rows."""

from __future__ import annotations

from typing import Dict, List, Tuple

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
    return any(token.isupper() or any(ch.isdigit() for ch in token) for token in tokens)


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
            prev_prov = set(prev.get("provenance", []))
            new_prov = set(row.get("provenance", []))
            prev["provenance"] = sorted(prev_prov | new_prov)
            continue
        seen[key] = row
        valid.append(row)
    return valid, report
