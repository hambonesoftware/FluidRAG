"""Shared loader for the atomic extraction prompt."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Tuple


@lru_cache(maxsize=1)
def load_atomic_prompt() -> Tuple[str, str]:
    path = Path(__file__).with_name("atomic_extraction.txt")
    text = path.read_text(encoding="utf-8")
    if "User:" not in text:
        return text.strip(), ""
    system_part, user_part = text.split("User:", 1)
    system_prompt = system_part.replace("System:", "", 1).strip()
    user_template = user_part.strip()
    return system_prompt, user_template


def atomic_system_prompt() -> str:
    return load_atomic_prompt()[0]


def atomic_user_template() -> str:
    return load_atomic_prompt()[1]


__all__ = ["load_atomic_prompt", "atomic_system_prompt", "atomic_user_template"]
