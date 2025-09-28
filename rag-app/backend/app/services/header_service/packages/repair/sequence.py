"""Repair header sequences."""
from __future__ import annotations

from dataclasses import replace
from typing import List

from backend.app.contracts.headers import Header


def repair_sequence(headers: List[Header]) -> List[Header]:
    if not headers:
        return headers
    repaired: List[Header] = []
    last_level = 1
    for header in headers:
        level = header.level
        if level - last_level > 1:
            level = last_level + 1
        repaired.append(replace(header, level=level))
        last_level = level
    return repaired
