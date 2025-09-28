"""Electrical engineering prompt template."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    """Holds system/user prompt strings for a pass."""

    system: str = (
        "You are an electrical engineering reviewer with expertise in power "
        "distribution, signal integrity, and safety compliance."
    )
    user: str = (
        "Summarise electrical considerations, including power budgets, cabling, "
        "and safety constraints. Cite chunk ids."
    )

    def render(self, context: str) -> tuple[str, str]:
        return self.system, f"{self.user}\n\nContext:\n{context}"


__all__ = ["Prompt"]
