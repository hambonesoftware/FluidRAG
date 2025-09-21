from __future__ import annotations

import logging
import traceback
from typing import Any

log = logging.getLogger("FluidRAG.strings")


def s(value: Any) -> str:
    """Return a stripped string for ``value`` while tolerating ``None`` and non-strings."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def sn(value: Any, *, label: str, req_id: str = "-") -> str:
    """Safe string conversion that logs when ``value`` is unexpected."""

    if value is None:
        log.error(
            "[sn %s] %s is None (unexpected). Caller:\n%s",
            req_id,
            label,
            "".join(traceback.format_stack(limit=4)),
        )
        return ""
    if isinstance(value, str):
        return value.strip()
    log.warning(
        "[sn %s] %s is type=%s (auto-stringify). Caller:\n%s",
        req_id,
        label,
        type(value).__name__,
        "".join(traceback.format_stack(limit=3)),
    )
    return str(value).strip()
