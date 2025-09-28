"""Controls prompt."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    name: str = "controls"
    question: str = "Describe control strategies or feedback loops referenced."
