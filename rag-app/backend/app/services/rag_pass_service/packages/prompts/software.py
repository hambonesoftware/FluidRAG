"""Software prompt."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    name: str = "software"
    question: str = "Identify software or computational workflows mentioned."
