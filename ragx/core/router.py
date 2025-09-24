"""Context-aware profile router."""

from __future__ import annotations

from copy import deepcopy


def pick_profile(ppass: str, intent: str, profiles_yaml: dict) -> dict:
    passes = profiles_yaml.get("passes", {})
    base = passes.get(ppass)
    if base is None:
        raise KeyError(f"Unknown pass: {ppass}")
    profile = deepcopy(base)
    if intent == "HEADER":
        profile.setdefault("retrieval", {}).setdefault("cascade", ["sparse"])
    return profile
