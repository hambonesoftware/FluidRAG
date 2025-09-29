"""Audit helpers for building normalized stage records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _current_correlation_id() -> str | None:
    try:
        from .logging import get_correlation_id

        return get_correlation_id()
    except Exception:  # pragma: no cover - defensive against circular import
        return None


def stage_record(
    *,
    stage: str,
    status: str = "ok",
    correlation_id: str | None = None,
    duration_ms: float | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build a normalized stage audit record with optional timings."""

    now = datetime.now(tz=timezone.utc)
    ended = ended_at or now
    started = started_at or ended
    derived_duration: float | None = None
    if duration_ms is not None:
        derived_duration = float(duration_ms)
    elif ended and started:
        derived_duration = (ended - started).total_seconds() * 1000.0

    record: dict[str, Any] = {
        "stage": stage,
        "status": status,
        "timestamp": ended.isoformat(),
    }
    corr = correlation_id or _current_correlation_id()
    if corr:
        record["correlation_id"] = corr
    if derived_duration is not None:
        record["duration_ms"] = round(derived_duration, 3)
    for key, value in kwargs.items():
        if value is not None:
            record[key] = value
    return record


__all__ = ["stage_record"]
