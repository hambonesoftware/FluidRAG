"""Detect list structures."""
from __future__ import annotations

from typing import Dict, List

from backend.app.contracts.parsing import TextBlock


def detect_lists_bullets(blocks: List[TextBlock]) -> Dict[int, bool]:
    markers = {"-", "*"}
    results: Dict[int, bool] = {}
    for idx, block in enumerate(blocks):
        lines = [line.strip() for line in block.content.splitlines() if line.strip()]
        results[idx] = any(line.split()[0] in markers for line in lines if len(line.split()) > 1)
    return results
