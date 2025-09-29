"""Filesystem utilities for persisting pipeline artifacts."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterable
from pathlib import Path
from typing import Any

from ..util.logging import get_logger

logger = get_logger(__name__)


def ensure_parent_dirs(path: str) -> None:
    """Create parent directories for *path* if they do not already exist."""

    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: str, payload: dict[str, Any]) -> None:
    """Write a JSON file with directories ensured."""

    ensure_parent_dirs(path)
    target = Path(path)
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.debug("storage.write_json", extra={"path": str(target)})


def write_jsonl(path: str, rows: Iterable[dict[str, Any]]) -> None:
    """Write JSONL lines safely."""

    ensure_parent_dirs(path)
    target = Path(path)
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    text = "\n".join(lines)
    if lines:
        text += "\n"
    target.write_text(text, encoding="utf-8")
    logger.debug("storage.write_jsonl", extra={"path": str(target), "rows": len(lines)})


def read_jsonl(path: str) -> list[dict[str, Any]]:
    """Read JSONL into list of dicts."""

    target = Path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            logger.warning(
                "storage.read_jsonl.decode_failed",
                extra={"path": str(target), "error": str(exc)},
            )
    return rows


async def stream_read(path: str, chunk_size: int = 65536) -> AsyncIterator[bytes]:
    """Async stream file bytes in chunks from disk."""

    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(path)

    with target.open("rb") as handle:
        while True:
            chunk = await asyncio.to_thread(handle.read, chunk_size)
            if not chunk:
                break
            yield chunk


async def stream_write(path: str, aiter: AsyncIterator[bytes]) -> None:
    """Async write bytes from stream to file."""

    ensure_parent_dirs(path)
    target = Path(path)
    with target.open("wb") as handle:
        async for chunk in aiter:
            if not chunk:
                continue
            await asyncio.to_thread(handle.write, chunk)
    logger.debug("storage.stream_write", extra={"path": str(target)})


__all__ = [
    "ensure_parent_dirs",
    "write_json",
    "write_jsonl",
    "read_jsonl",
    "stream_read",
    "stream_write",
]
