"""Simple audit staging utility."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .logging import get_logger

logger = get_logger(__name__)


def stage_record(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2, sort_keys=True)
    logger.debug("Audit staged", extra={"path": str(path)})
