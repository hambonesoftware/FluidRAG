"""Storage adapter for reading/writing pipeline artifacts."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterable, List

from backend.app.config import settings
from backend.app.util.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class StorageAdapter:
    """Small helper around the artifact storage directory.

    The original project exposed a module-level ``storage`` object with
    convenience methods such as :meth:`write_json`.  Several services import
    that object directly, so the adapter keeps the same public surface while
    routing all filesystem interactions through a single, well-tested
    implementation.
    """

    base_dir: Path

    def __init__(self, base_dir: Path | None = None) -> None:
        base_dir = (base_dir or settings.storage_dir).resolve()
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _resolve(self, path: str | Path) -> Path:
        resolved = (self.base_dir / path).resolve()
        if not str(resolved).startswith(str(self.base_dir)):
            raise ValueError("Path traversal detected")
        return resolved

    def _ensure_parent_dirs(self, path: str | Path) -> Path:
        resolved = self._resolve(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    def write_json(self, path: str | Path, payload: Dict[str, Any]) -> Path:
        resolved = self._ensure_parent_dirs(path)
        with resolved.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        logger.debug("write_json", extra={"path": str(resolved)})
        return resolved

    def write_jsonl(self, path: str | Path, rows: Iterable[Dict[str, Any]]) -> Path:
        resolved = self._ensure_parent_dirs(path)
        with resolved.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
        logger.debug("write_jsonl", extra={"path": str(resolved)})
        return resolved

    def read_jsonl(self, path: str | Path) -> List[Dict[str, Any]]:
        resolved = self._resolve(path)
        if not resolved.exists():
            return []
        with resolved.open("r", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def write_bytes(self, path: str | Path, data: bytes) -> Path:
        resolved = self._ensure_parent_dirs(path)
        resolved.write_bytes(data)
        return resolved

    def read_json(self, path: str | Path) -> Dict[str, Any]:
        resolved = self._resolve(path)
        with resolved.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def stream_path(self, path: str | Path) -> Path:
        return self._resolve(path)

    async def stream_read(self, path: str | Path, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        resolved = self._resolve(path)
        loop = asyncio.get_running_loop()

        def _reader() -> bytes:
            return resolved.read_bytes()

        data = await loop.run_in_executor(None, _reader)
        for idx in range(0, len(data), chunk_size):
            yield data[idx : idx + chunk_size]

    async def stream_write(self, path: str | Path, aiter: AsyncIterator[bytes]) -> None:
        resolved = self._ensure_parent_dirs(path)
        loop = asyncio.get_running_loop()
        chunks: List[bytes] = []
        async for chunk in aiter:
            chunks.append(chunk)

        def _writer() -> None:
            resolved.write_bytes(b"".join(chunks))

        await loop.run_in_executor(None, _writer)


# Backwards compatible module-level helpers ---------------------------------
storage = StorageAdapter()


def ensure_parent_dirs(path: str | Path) -> None:
    storage._ensure_parent_dirs(path)


def write_json(path: str | Path, payload: Dict[str, Any]) -> Path:
    return storage.write_json(path, payload)


def write_jsonl(path: str | Path, rows: Iterable[Dict[str, Any]]) -> Path:
    return storage.write_jsonl(path, rows)


def read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    return storage.read_jsonl(path)


def write_bytes(path: str | Path, data: bytes) -> Path:
    return storage.write_bytes(path, data)


def read_json(path: str | Path) -> Dict[str, Any]:
    return storage.read_json(path)


def stream_path(path: str | Path) -> Path:
    return storage.stream_path(path)


async def stream_read(path: str | Path, chunk_size: int = 65536) -> AsyncIterator[bytes]:
    async for chunk in storage.stream_read(path, chunk_size=chunk_size):
        yield chunk


async def stream_write(path: str | Path, aiter: AsyncIterator[bytes]) -> None:
    await storage.stream_write(path, aiter)
