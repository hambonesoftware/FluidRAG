"""Software prompt template."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    """Holds system/user prompt strings for a pass."""

    system: str = (
        "You are a software architecture reviewer focusing on APIs, telemetry, "
        "and risk mitigation."
    )
    user: str = (
        "Summarise software behaviours, interfaces, and testing hooks. "
        "Cite chunk ids."
    )

    def render(self, context: str) -> tuple[str, str]:
        return self.system, f"{self.user}\n\nContext:\n{context}"


__all__ = ["Prompt"]
