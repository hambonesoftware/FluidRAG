"""Electrical engineering prompt."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    name: str = "electrical"
    question: str = "Highlight electrical systems considerations discussed in the document."
