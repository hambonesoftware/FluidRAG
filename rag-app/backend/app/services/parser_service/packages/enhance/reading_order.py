"""Build reading order metadata."""
from __future__ import annotations

from typing import List

from backend.app.contracts.parsing import TextBlock


def build_reading_order(blocks: List[TextBlock]) -> List[TextBlock]:
    return sorted(blocks, key=lambda block: (block.page, block.order))
