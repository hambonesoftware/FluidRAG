"""Build a normalized stage audit record."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


def stage_record(**kwargs: Any) -> Dict[str, Any]:
    """Build a normalized stage audit record."""
    stage = kwargs.pop("stage", "unknown")
    status = kwargs.pop("status", "ok")
    record: Dict[str, Any] = {
        "stage": stage,
        "status": status,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    for key, value in kwargs.items():
        if value is not None:
            record[key] = value
    return record


__all__ = ["stage_record"]
