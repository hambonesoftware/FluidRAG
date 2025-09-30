"""File storage helpers and guarded adapters."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..util.logging import get_logger

logger = get_logger(__name__)


@dataclass
class StorageEvent:
    """Audit record describing a managed storage operation."""

    doc_id: str | None
    path: Path
    operation: str


class StorageWriteGuard:
    """Track managed writes and detect unguarded PDF persistence."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._events: list[StorageEvent] = []

    def record(self, *, doc_id: str | None, path: Path, operation: str) -> None:
        event = StorageEvent(doc_id=doc_id, path=path.resolve(), operation=operation)
        self._events.append(event)

    def recorded_paths(self) -> set[Path]:
        return {event.path for event in self._events}

    def calls_for(self, doc_id: str) -> int:
        return sum(1 for event in self._events if event.doc_id == doc_id)

    @property
    def called(self) -> bool:
        return bool(self._events)

    def assert_no_unmanaged_pdfs(self, root: Path) -> None:
        """Raise if any PDF exists under *root* without a managed record."""

        recorded_pdf_paths = {
            event.path for event in self._events if event.path.suffix.lower() == ".pdf"
        }
        for pdf_path in root.rglob("*.pdf"):
            resolved = pdf_path.resolve()
            if resolved not in recorded_pdf_paths:
                raise RuntimeError(f"unmanaged PDF write detected: {resolved}")


_STORAGE_GUARD = StorageWriteGuard()


def get_storage_guard() -> StorageWriteGuard:
    """Return the singleton storage guard."""

    return _STORAGE_GUARD


def reset_storage_guard() -> None:
    """Clear the storage guard audit trail."""

    _STORAGE_GUARD.reset()


def assert_no_unmanaged_writes() -> None:
    """Ensure all persisted PDFs were recorded by the storage adapter."""

    root = get_settings().artifact_root_path
    _STORAGE_GUARD.assert_no_unmanaged_pdfs(root)


class StorageAdapter:
    """Adapter responsible for persisting upload-stage artifacts."""

    def __init__(self, root: Path | None = None) -> None:
        settings = get_settings()
        self.root = Path(root) if root is not None else settings.artifact_root_path

    def _doc_root(self, doc_id: str) -> Path:
        doc_root = Path(self.root) / doc_id
        doc_root.mkdir(parents=True, exist_ok=True)
        return doc_root

    def save_source_pdf(
        self, *, doc_id: str, filename: str | None, payload: bytes
    ) -> Path:
        """Persist the uploaded PDF payload in managed storage."""

        target = self._doc_root(doc_id) / "source.pdf"
        target.write_bytes(payload)
        logger.info(
            "storage.save_source_pdf",
            extra={
                "doc_id": doc_id,
                "path": str(target),
                "bytes": len(payload),
                "upload_filename": filename or "source.pdf",
            },
        )
        _STORAGE_GUARD.record(doc_id=doc_id, path=target, operation="save_source_pdf")
        return target

    def save_json(self, *, doc_id: str, name: str, payload: dict[str, Any]) -> Path:
        """Persist a JSON artifact within the document directory."""

        target = self._doc_root(doc_id) / name
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.debug(
            "storage.save_json",
            extra={"doc_id": doc_id, "path": str(target)},
        )
        _STORAGE_GUARD.record(doc_id=doc_id, path=target, operation="save_json")
        return target


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


async def stream_read(path: str, chunk_size: int | None = None) -> AsyncIterator[bytes]:
    """Async stream file bytes in chunks from disk."""

    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(path)

    effective_chunk = (
        chunk_size if chunk_size is not None else get_settings().storage_chunk_bytes()
    )
    with target.open("rb") as handle:
        while True:
            chunk = await asyncio.to_thread(handle.read, effective_chunk)
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
    "StorageAdapter",
    "assert_no_unmanaged_writes",
    "ensure_parent_dirs",
    "get_storage_guard",
    "read_jsonl",
    "reset_storage_guard",
    "stream_read",
    "stream_write",
    "write_json",
    "write_jsonl",
]
