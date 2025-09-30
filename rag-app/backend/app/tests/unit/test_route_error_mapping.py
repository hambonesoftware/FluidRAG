"""Tests ensuring route-level error mapping is correct."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import HTTPException

from ...routes import chunk, headers, parser, upload
from ...services.chunk_service import ChunkResult, run_uf_chunking
from ...services.header_service import HeaderJoinResult, join_and_rechunk
from ...services.parser_service import ParseResult, parse_and_enrich
from ...services.upload_service import NormalizedDoc, ensure_normalized
from ...util.errors import AppError, NotFoundError, ValidationError


def _make_normalized_doc() -> NormalizedDoc:
    return NormalizedDoc(
        doc_id="doc",
        normalized_path="/tmp/normalize.json",
        manifest_path="/tmp/manifest.json",
        source_checksum="abc123",
        source_bytes=10,
    )


def _make_chunk_result() -> ChunkResult:
    return ChunkResult(
        doc_id="doc",
        chunks_path="/tmp/chunks.jsonl",
        chunk_count=1,
        index_manifest_path="/tmp/index.json",
    )


def _make_parse_result() -> ParseResult:
    return ParseResult(doc_id="doc", enriched_path="/tmp/parse.json")


def _make_header_result() -> HeaderJoinResult:
    return HeaderJoinResult(
        doc_id="doc",
        headers_path="/tmp/headers.json",
        section_map_path="/tmp/section_map.json",
        header_chunks_path="/tmp/header_chunks.jsonl",
        header_count=3,
        recovered_count=2,
    )


def test_upload_route_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_in_threadpool(func: Callable[..., Any], *args: Any) -> Any:
        assert func is ensure_normalized
        return _make_normalized_doc()

    monkeypatch.setattr(upload, "run_in_threadpool", fake_run_in_threadpool)
    response = asyncio.run(
        upload.normalize_upload(upload.UploadRequest(file_name="doc.pdf"))
    )
    assert response.doc_id == "doc"


@pytest.mark.parametrize(
    "exc, status",
    [
        (ValidationError("bad"), 400),
        (NotFoundError("missing"), 404),
        (AppError("fail"), 500),
    ],
)
def test_upload_route_error_mapping(
    monkeypatch: pytest.MonkeyPatch, exc: AppError, status: int
) -> None:
    async def fake_run_in_threadpool(*_: Any, **__: Any) -> Any:
        raise exc

    monkeypatch.setattr(upload, "run_in_threadpool", fake_run_in_threadpool)

    with pytest.raises(HTTPException) as captured:
        asyncio.run(upload.normalize_upload(upload.UploadRequest(file_name="doc.pdf")))

    assert captured.value.status_code == status
    assert str(exc) in captured.value.detail


def test_chunk_route_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_in_threadpool(func: Callable[..., Any], *args: Any) -> Any:
        assert func is run_uf_chunking
        return _make_chunk_result()

    monkeypatch.setattr(chunk, "run_in_threadpool", fake_run_in_threadpool)
    payload = chunk.ChunkRequest(doc_id="doc", normalize_artifact="/tmp/normalize.json")
    response = asyncio.run(chunk.chunk_document(payload))
    assert response.chunk_count == 1


@pytest.mark.parametrize(
    "exc, status",
    [
        (ValidationError("bad"), 400),
        (NotFoundError("missing"), 404),
        (AppError("fail"), 500),
    ],
)
def test_chunk_route_error_mapping(
    monkeypatch: pytest.MonkeyPatch, exc: AppError, status: int
) -> None:
    async def fake_run_in_threadpool(*_: Any, **__: Any) -> Any:
        raise exc

    monkeypatch.setattr(chunk, "run_in_threadpool", fake_run_in_threadpool)
    payload = chunk.ChunkRequest(doc_id="doc", normalize_artifact="/tmp/normalize.json")

    with pytest.raises(HTTPException) as captured:
        asyncio.run(chunk.chunk_document(payload))

    assert captured.value.status_code == status


def test_parser_route_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_in_threadpool(func: Callable[..., Any], *args: Any) -> Any:
        assert func is parse_and_enrich
        return _make_parse_result()

    monkeypatch.setattr(parser, "run_in_threadpool", fake_run_in_threadpool)
    payload = parser.ParserRequest(
        doc_id="doc", normalize_artifact="/tmp/normalize.json"
    )
    response = asyncio.run(parser.enrich_document(payload))
    assert response.doc_id == "doc"


@pytest.mark.parametrize(
    "exc, status",
    [
        (ValidationError("bad"), 400),
        (NotFoundError("missing"), 404),
        (AppError("fail"), 500),
    ],
)
def test_parser_route_error_mapping(
    monkeypatch: pytest.MonkeyPatch, exc: AppError, status: int
) -> None:
    async def fake_run_in_threadpool(*_: Any, **__: Any) -> Any:
        raise exc

    monkeypatch.setattr(parser, "run_in_threadpool", fake_run_in_threadpool)
    payload = parser.ParserRequest(
        doc_id="doc", normalize_artifact="/tmp/normalize.json"
    )

    with pytest.raises(HTTPException) as captured:
        asyncio.run(parser.enrich_document(payload))

    assert captured.value.status_code == status


def test_header_route_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_in_threadpool(func: Callable[..., Any], *args: Any) -> Any:
        assert func is join_and_rechunk
        return _make_header_result()

    monkeypatch.setattr(headers, "run_in_threadpool", fake_run_in_threadpool)
    payload = headers.HeaderJoinRequest(
        doc_id="doc", chunks_artifact="/tmp/chunks.json"
    )
    response = asyncio.run(headers.join_headers(payload))
    assert response.headers_path.endswith("headers.json")


@pytest.mark.parametrize(
    "exc, status",
    [
        (ValidationError("bad"), 400),
        (NotFoundError("missing"), 404),
        (AppError("fail"), 500),
    ],
)
def test_header_route_error_mapping(
    monkeypatch: pytest.MonkeyPatch, exc: AppError, status: int
) -> None:
    async def fake_run_in_threadpool(*_: Any, **__: Any) -> Any:
        raise exc

    monkeypatch.setattr(headers, "run_in_threadpool", fake_run_in_threadpool)
    payload = headers.HeaderJoinRequest(
        doc_id="doc", chunks_artifact="/tmp/chunks.json"
    )

    with pytest.raises(HTTPException) as captured:
        asyncio.run(headers.join_headers(payload))

    assert captured.value.status_code == status
