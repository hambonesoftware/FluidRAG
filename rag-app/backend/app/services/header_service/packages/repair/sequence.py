"""Sequence repair for header gaps."""

from __future__ import annotations

from typing import Any

from .....util.logging import get_logger

logger = get_logger(__name__)

_MIN_STRONG_SCORE = 0.55
_MIN_RECOVERY_SCORE = 0.35


def _as_int_ordinal(value: Any) -> int | None:
    """Safely convert an ordinal value into an integer if possible."""

    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
            key=lambda h: (_as_int_ordinal(h.get("ordinal")) or 0, h.get("chunk_index", 0)),
        )
        strong = [h for h in ordered if float(h.get("score", 0.0)) >= _MIN_STRONG_SCORE]
        weak = [
            h
            for h in ordered
            if _MIN_RECOVERY_SCORE <= float(h.get("score", 0.0)) < _MIN_STRONG_SCORE
        ]
        weak_lookup: dict[int, dict[str, Any]] = {}
        for weak_header in weak:
            ordinal_int = _as_int_ordinal(weak_header.get("ordinal"))
            if ordinal_int is None:
                continue
            existing = weak_lookup.get(ordinal_int)
            if existing is None or float(weak_header.get("score", 0.0)) > float(
                existing.get("score", 0.0)
            ):
                weak_lookup[ordinal_int] = weak_header
        if not strong:
            # Promote the best weak candidate to ensure coverage if it looks plausible.
            if weak:
                best = max(weak, key=lambda h: float(h.get("score", 0.0)))
                best = dict(best)
                best["recovered"] = True
                strong.append(best)
        recovered_ordinals: set[int] = set()
        strong_sorted = sorted(
            strong,
            key=lambda h: (_as_int_ordinal(h.get("ordinal")) or 0, h.get("chunk_index", 0)),
        )
        for i, header in enumerate(strong_sorted):
            repaired.append(header)
            current_ord = _as_int_ordinal(header.get("ordinal"))
            if current_ord is None:
                continue
            next_ord = None
            if i + 1 < len(strong_sorted):
                next_ord = _as_int_ordinal(strong_sorted[i + 1].get("ordinal"))
            if next_ord is None:
                continue
            gap = next_ord - current_ord
            if gap <= 1:
                continue
            for missing in range(current_ord + 1, next_ord):
                if missing in recovered_ordinals:
                    continue
                candidate = weak_lookup.get(missing)
                if candidate:
                    candidate = dict(candidate)
                    candidate["recovered"] = True
                    candidate["score"] = max(
                        candidate.get("score", 0.0), _MIN_RECOVERY_SCORE
                    )
                    recovered_ordinals.add(missing)
                    repaired.append(candidate)
        ordinal_values = [
            ordinal
            for header in strong_sorted
            if (ordinal := _as_int_ordinal(header.get("ordinal"))) is not None
        ]
        if ordinal_values:
            min_strong = min(ordinal_values)
            max_strong = max(ordinal_values)
            for missing in sorted(
                ord_val
                for ord_val in weak_lookup
                if ord_val < min_strong and ord_val not in recovered_ordinals
            ):
                candidate = dict(weak_lookup[missing])
                candidate["recovered"] = True
                candidate["score"] = max(
                    candidate.get("score", 0.0), _MIN_RECOVERY_SCORE
                )
                recovered_ordinals.add(missing)
                repaired.append(candidate)
            for missing in sorted(
                ord_val
                for ord_val in weak_lookup
                if ord_val > max_strong and ord_val not in recovered_ordinals
            ):
                candidate = dict(weak_lookup[missing])
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
    repaired.sort(
        key=lambda h: (
            h.get("chunk_index", 0),
            _as_int_ordinal(h.get("ordinal")) or 0,
        )
    )
    return repaired


__all__ = ["repair_sequence"]
