"""List detection heuristics."""

from __future__ import annotations

import re
from typing import Any

_BULLET_PATTERN = re.compile(r"^(?P<prefix>(\d+\.|[\-*]))\s+(?P<body>.+)")


def detect_lists_bullets(text_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect ordered/unordered lists & bullets."""
    lists: list[dict[str, Any]] = []
    for block in text_blocks:
        lines = [
            line.strip() for line in block.get("text", "").splitlines() if line.strip()
        ]
        items: list[dict[str, Any]] = []
        ordered = True
        for line in lines:
            match = _BULLET_PATTERN.match(line)
            if not match:
                continue
            prefix = match.group("prefix")
            if not prefix.endswith("."):
                ordered = False
            items.append({"text": match.group("body"), "prefix": prefix})
        if items:
            lists.append(
                {
                    "anchor_block": block.get("id"),
                    "ordered": ordered,
                    "items": items,
                }
            )
    return lists
