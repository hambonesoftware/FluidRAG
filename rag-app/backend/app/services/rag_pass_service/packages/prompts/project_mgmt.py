"""Project management prompt."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    name: str = "project_mgmt"
    question: str = "Summarize project management risks or timelines referenced."
