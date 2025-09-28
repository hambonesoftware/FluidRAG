"""High entropy/energy scoring heuristics."""

from __future__ import annotations

from typing import Any


def energy_score(chunk: dict[str, Any]) -> float:
    """High-entropy/variance scoring for spec-dense spans."""

    text = str(chunk.get("text", ""))
    if not text:
        return 0.0
    digits = sum(char.isdigit() for char in text)
    capitals = sum(char.isupper() for char in text)
    specials = sum(char in {"%", "°", "±"} for char in text)
    return round((digits + capitals + specials) / max(len(text), 1), 4)


__all__ = ["energy_score"]
