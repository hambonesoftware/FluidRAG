"""Sequence repair for header gaps."""

from __future__ import annotations

from typing import Any

from .....util.logging import get_logger

logger = get_logger(__name__)

_MIN_STRONG_SCORE = 0.55
_MIN_RECOVERY_SCORE = 0.35


def _series_bucket(header: dict[str, Any]) -> str:
    return str(header.get("section_key") or "root").lower()


def repair_sequence(headers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggressive hole detection & recovery (e.g., A5/A6)."""

    if not headers:
        return []
    buckets: dict[str, list[dict[str, Any]]] = {}
    for header in headers:
        buckets.setdefault(_series_bucket(header), []).append(header)
    repaired: list[dict[str, Any]] = []
    for series, series_headers in buckets.items():
        ordered = sorted(
            series_headers,
            key=lambda h: (h.get("ordinal") or 0, h.get("chunk_index", 0)),
        )
        strong = [h for h in ordered if float(h.get("score", 0.0)) >= _MIN_STRONG_SCORE]
        weak = [
            h
            for h in ordered
            if _MIN_RECOVERY_SCORE <= float(h.get("score", 0.0)) < _MIN_STRONG_SCORE
        ]
        if not strong:
            # Promote the best weak candidate to ensure coverage if it looks plausible.
            if weak:
                best = max(weak, key=lambda h: float(h.get("score", 0.0)))
                best = dict(best)
                best["recovered"] = True
                strong.append(best)
        recovered_ordinals: set[int] = set()
        strong_sorted = sorted(
            strong, key=lambda h: (h.get("ordinal") or 0, h.get("chunk_index", 0))
        )
        for i, header in enumerate(strong_sorted):
            repaired.append(header)
            current_ord = header.get("ordinal")
            if current_ord is None:
                continue
            next_ord = None
            if i + 1 < len(strong_sorted):
                next_ord = strong_sorted[i + 1].get("ordinal")
            if next_ord is None:
                continue
            gap = int(next_ord) - int(current_ord)
            if gap <= 1:
                continue
            for missing in range(int(current_ord) + 1, int(next_ord)):
                if missing in recovered_ordinals:
                    continue
                candidate = None
                for weak_header in weak:
                    if int(weak_header.get("ordinal") or -1) == missing:
                        candidate = dict(weak_header)
                        break
                if candidate:
                    candidate["recovered"] = True
                    candidate["score"] = max(
                        candidate.get("score", 0.0), _MIN_RECOVERY_SCORE
                    )
                    recovered_ordinals.add(missing)
                    repaired.append(candidate)
        logger.debug(
            "headers.repair.series",
            extra={
                "series": series,
                "strong": len(strong_sorted),
                "weak": len(weak),
                "recovered": len(recovered_ordinals),
            },
        )
    repaired.sort(key=lambda h: (h.get("chunk_index", 0), h.get("ordinal") or 0))
    return repaired


__all__ = ["repair_sequence"]
