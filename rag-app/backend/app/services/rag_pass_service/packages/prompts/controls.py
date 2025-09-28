"""Controls/automation prompt template."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    """Holds system/user prompt strings for a pass."""

    system: str = (
        "You are a controls engineer analysing loops, actuation, and "
        "fault detection strategies."
    )
    user: str = (
        "Summarise control strategies, sensing, and monitoring requirements. "
        "Cite chunk ids."
    )

    def render(self, context: str) -> tuple[str, str]:
        return self.system, f"{self.user}\n\nContext:\n{context}"


__all__ = ["Prompt"]
