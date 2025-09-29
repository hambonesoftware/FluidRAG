"""Tests for storage adapter helpers."""

from __future__ import annotations

import asyncio
import io
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from ...adapters import storage


def test_write_and_read_json_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "payload.json"
    payload = {"value": 42, "text": "hello"}

    storage.write_json(str(target), payload)

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data == payload


def test_write_jsonl_and_read_handles_invalid_rows(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    target = tmp_path / "nested" / "rows.jsonl"
    rows = [{"idx": 1}, {"idx": 2}]

    storage.write_jsonl(str(target), rows)

    # Append an invalid line and an empty line to exercise warnings/skip paths.
    with target.open("a", encoding="utf-8") as handle:
        handle.write("{invalid}\n\n")

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    storage.logger.handlers = [handler]
    storage.logger.setLevel(logging.WARNING)
    storage.logger.propagate = False
    loaded = storage.read_jsonl(str(target))

    assert loaded == rows
    handler.flush()
    assert "storage.read_jsonl.decode_failed" in stream.getvalue()


def test_read_jsonl_missing_returns_empty(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jsonl"
    assert storage.read_jsonl(str(missing)) == []


def test_stream_write_and_read(tmp_path: Path) -> None:
    target = tmp_path / "stream.bin"

    async def producer() -> AsyncIterator[bytes]:
        for chunk in (b"hello", b"", b" world"):
            yield chunk

    asyncio.run(storage.stream_write(str(target), producer()))

    async def _collect() -> list[bytes]:
        return [chunk async for chunk in storage.stream_read(str(target))]

    chunks = asyncio.run(_collect())
    assert b"".join(chunks) == b"hello world"


def test_stream_read_missing_raises(tmp_path: Path) -> None:
    missing = tmp_path / "nope.bin"

    async def _consume() -> None:
        async for _ in storage.stream_read(str(missing)):
            raise AssertionError("stream should not yield when file missing")

    with pytest.raises(FileNotFoundError):
        asyncio.run(_consume())
