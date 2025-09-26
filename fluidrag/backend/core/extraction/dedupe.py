"""De-duplication helpers for atomic requirement records."""
from __future__ import annotations

from typing import Dict, Iterable, List, Set, Tuple


def dedupe(records: Iterable[Dict]) -> List[Dict]:
    seen: Set[Tuple] = set()
    unique: List[Dict] = []

    for record in records:
        key = (record.get("section_id"), record.get("text"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)

    return unique


__all__ = ["dedupe"]
