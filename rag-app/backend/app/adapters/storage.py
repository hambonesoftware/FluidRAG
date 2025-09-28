"""Storage adapter for reading/writing pipeline artifacts."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterable, List

from backend.app.config import settings
from backend.app.util.logging import get_logger

logger = get_logger(__name__)


def _resolve(path: str | Path) -> Path:
    base = settings.storage_dir
    resolved = (base / path).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise ValueError("Path traversal detected")
    return resolved


def ensure_parent_dirs(path: str | Path) -> None:
    """Create parent directories if missing."""

    resolved = _resolve(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: str | Path, payload: Dict[str, Any]) -> None:
    """Write a JSON file with directories ensured."""

    resolved = _resolve(path)
    ensure_parent_dirs(resolved)
    with resolved.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
    logger.debug("write_json", extra={"path": str(resolved)})


def write_jsonl(path: str | Path, rows: Iterable[Dict[str, Any]]) -> None:
    """Write JSONL lines safely."""

    resolved = _resolve(path)
    ensure_parent_dirs(resolved)
    with resolved.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    logger.debug("write_jsonl", extra={"path": str(resolved)})


def read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    """Read JSONL into list of dicts."""

    resolved = _resolve(path)
    if not resolved.exists():
        return []
    with resolved.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_bytes(path: str | Path, data: bytes) -> None:
    resolved = _resolve(path)
    ensure_parent_dirs(resolved)
    resolved.write_bytes(data)


def read_json(path: str | Path) -> Dict[str, Any]:
    resolved = _resolve(path)
    with resolved.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def stream_path(path: str | Path) -> Path:
    return _resolve(path)


async def stream_read(path: str | Path, chunk_size: int = 65536) -> AsyncIterator[bytes]:
    """Async stream file bytes in chunks."""

    resolved = _resolve(path)
    loop = asyncio.get_running_loop()

    def _reader() -> bytes:
        return resolved.read_bytes()

    data = await loop.run_in_executor(None, _reader)
    for idx in range(0, len(data), chunk_size):
        yield data[idx : idx + chunk_size]


async def stream_write(path: str | Path, aiter: AsyncIterator[bytes]) -> None:
    """Async write bytes from stream to file."""

    resolved = _resolve(path)
    ensure_parent_dirs(resolved)
    loop = asyncio.get_running_loop()
    chunks: List[bytes] = []
    async for chunk in aiter:
        chunks.append(chunk)

    def _writer() -> None:
        resolved.write_bytes(b"".join(chunks))

    await loop.run_in_executor(None, _writer)
