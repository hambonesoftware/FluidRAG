"""Mechanical engineering prompt."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    name: str = "mechanical"
    question: str = "Summarize mechanical insights relevant to the document."
