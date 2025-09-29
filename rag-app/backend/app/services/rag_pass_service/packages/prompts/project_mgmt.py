"""Project management prompt template."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    """Holds system/user prompt strings for a pass."""

    system: str = (
        "You are a project/program manager highlighting risks, dependencies, "
        "and schedule impacts."
    )
    user: str = (
        "Summarise programme risks, stakeholder actions, and next steps. "
        "Cite chunk ids."
    )

    def render(self, context: str) -> tuple[str, str]:
        return self.system, f"{self.user}\n\nContext:\n{context}"


__all__ = ["Prompt"]
