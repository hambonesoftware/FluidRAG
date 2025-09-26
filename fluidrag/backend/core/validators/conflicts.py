"""Conflict detection helpers for requirement records."""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Tuple


def find_conflicts(records: Iterable[Dict]) -> List[Dict]:
    buckets: defaultdict[Tuple, List[Dict]] = defaultdict(list)
    for record in records:
        key = (
            record.get("component") or record.get("device") or record.get("panel"),
            record.get("property") or record.get("rating_type"),
        )
        buckets[key].append(record)

    conflicts: List[Dict] = []
    for key, rows in buckets.items():
        ge_values = [row.get("value") for row in rows if row.get("op") in {"≥", ">="} and row.get("value") is not None]
        le_values = [row.get("value") for row in rows if row.get("op") in {"≤", "<="} and row.get("value") is not None]
        if ge_values and le_values and max(ge_values) > min(le_values):
            conflicts.append(
                {
                    "key": key,
                    "reason": "range_inconsistent",
                    "ge": max(ge_values),
                    "le": min(le_values),
                    "count": len(rows),
                }
            )
    return conflicts


__all__ = ["find_conflicts"]
