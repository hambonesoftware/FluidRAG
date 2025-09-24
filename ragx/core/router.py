"""Context-aware profile router."""

from __future__ import annotations

from copy import deepcopy


def pick_profile(ppass: str, intent: str, profiles_yaml: dict) -> dict:
    passes = profiles_yaml.get("passes", {})
    base = passes.get(ppass)
    if base is None:
        raise KeyError(f"Unknown pass: {ppass}")
    profile = deepcopy(base)
    retrieval = profile.setdefault("retrieval", {})

    if intent == "HEADER":
        retrieval["cascade"] = ["sparse"]
    elif intent in {"RETRIEVE", "COMPARE", "NUMERIC", "STANDARDS"}:
        cascade = retrieval.get("cascade", ["sparse", "dense_hyde", "colbert"])
        # ensure cascade follows the expected order without duplicates
        ordered = []
        for stage in ["sparse", "dense_hyde", "colbert", "cross"]:
            if stage in cascade and stage not in ordered:
                ordered.append(stage)
        retrieval["cascade"] = ordered
    else:
        retrieval["cascade"] = retrieval.get("cascade", ["sparse"])
    return profile
