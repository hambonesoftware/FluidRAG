"""Graph proximity heuristics for section navigation."""

from __future__ import annotations

from typing import Any


def graph_score(chunk: dict[str, Any]) -> float:
    """Graph proximity to header/section nodes."""

    path = str(chunk.get("header_path") or chunk.get("section_path") or "")
    if not path:
        return 0.5
    depth = path.count("/") + 1
    siblings = max(len(path.split("/")), 1)
    return round(1.0 / depth + 0.05 * siblings, 4)


__all__ = ["graph_score"]
