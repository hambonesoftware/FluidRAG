"""Infer semantics tags for text blocks."""
from __future__ import annotations

from typing import Dict, List

from backend.app.contracts.parsing import TextBlock


def infer_semantics(blocks: List[TextBlock]) -> Dict[int, str]:
    semantics: Dict[int, str] = {}
    for idx, block in enumerate(blocks):
        lowered = block.content.lower()
        if lowered.startswith("introduction"):
            semantics[idx] = "introduction"
        elif lowered.startswith("conclusion"):
            semantics[idx] = "conclusion"
        elif any(keyword in lowered for keyword in ["table", "figure", "result"]):
            semantics[idx] = "evidence"
        else:
            semantics[idx] = "body"
    return semantics
