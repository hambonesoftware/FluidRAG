"""Prompt registry for per-discipline extraction passes."""

from ..atomic import atomic_system_prompt


def _load_system_prompt() -> str:
    return atomic_system_prompt()


_SYSTEM_PROMPT = _load_system_prompt()

PASS_PROMPTS = {
    "Mechanical": _SYSTEM_PROMPT,
    "Electrical": _SYSTEM_PROMPT,
    "Controls": _SYSTEM_PROMPT,
    "Software": _SYSTEM_PROMPT,
    "Project Management": _SYSTEM_PROMPT,
}

__all__ = [
    "PASS_PROMPTS",
]
