"""Mechanical engineering prompt template."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    """Holds system/user prompt strings for a pass."""

    system: str = (
        "You are a mechanical engineering analyst producing factual, cited summaries."
    )
    user: str = (
        "Using the provided context, summarise mechanical design risks, loads, "
        "and interfaces. Cite chunk ids."
    )

    def render(self, context: str) -> tuple[str, str]:
        return self.system, f"{self.user}\n\nContext:\n{context}"


__all__ = ["Prompt"]
