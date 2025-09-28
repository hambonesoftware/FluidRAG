"""Pipeline orchestrator routes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, model_validator

from ..adapters import stream_read
from ..adapters.db import upsert_document_record
from ..config import get_settings
from ..services.chunk_service import run_uf_chunking
from ..services.header_service import join_and_rechunk
from ..services.parser_service import parse_and_enrich
from ..services.rag_pass_service import PassJobs
from ..services.rag_pass_service import run_all as run_passes
from ..services.upload_service import NormalizedDoc, ensure_normalized
from ..util.audit import stage_record
from ..util.errors import AppError, NotFoundError, ValidationError
from ..util.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class PipelineRunRequest(BaseModel):
    """Orchestrator pipeline input contract."""

    file_id: str | None = None
    file_name: str | None = None

    @model_validator(mode="after")
    def _ensure_source(self) -> PipelineRunRequest:
        if not (self.file_id or self.file_name):
            raise ValueError("file_id or file_name must be provided")
        return self


async def _load_json(path: str) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    return json.loads(target.read_text(encoding="utf-8"))


@router.post("/run", response_model=dict)
async def run_pipeline(req: PipelineRunRequest) -> dict[str, Any]:
    """Execute full pipeline: upload→parse→chunk→headers→passes."""

    try:
        normalized: NormalizedDoc = await run_in_threadpool(
            ensure_normalized, req.file_id, req.file_name
        )
        manifest = await _load_json(normalized.manifest_path)
        upsert_document_record(normalized.doc_id, normalized.normalized_path, manifest)

        parse_result = await run_in_threadpool(
            parse_and_enrich, normalized.doc_id, normalized.normalized_path
        )
        chunk_result = await run_in_threadpool(
            run_uf_chunking, normalized.doc_id, parse_result.enriched_path
        )
        headers_result = await run_in_threadpool(
            join_and_rechunk, normalized.doc_id, chunk_result.chunks_path
        )
        pass_jobs: PassJobs = await run_in_threadpool(
            run_passes, normalized.doc_id, headers_result.header_chunks_path
        )

        audit_path = (
            Path(get_settings().artifact_root_path)
            / normalized.doc_id
            / "pipeline.audit.json"
        )
        audit_path.write_text(
            json.dumps(
                stage_record(
                    stage="pipeline.run",
                    status="ok",
                    doc_id=normalized.doc_id,
                    passes=len(pass_jobs.passes),
                ),
                indent=2,
            ),
            encoding="utf-8",
        )

        return {
            "doc_id": normalized.doc_id,
            "normalize": normalized.model_dump(),
            "parse": parse_result.model_dump(),
            "chunks": chunk_result.model_dump(),
            "headers": headers_result.model_dump(),
            "passes": pass_jobs.model_dump(),
        }
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AppError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/status/{doc_id}", response_model=dict)
async def status(doc_id: str) -> dict[str, Any]:
    """Aggregate status for given document."""

    settings = get_settings()
    doc_root = Path(settings.artifact_root_path) / doc_id
    record_path = doc_root / "document.manifest.json"
    if not record_path.exists():
        raise HTTPException(status_code=404, detail="document not found")
    manifest = json.loads(record_path.read_text(encoding="utf-8"))
    passes_manifest_path = doc_root / "passes" / "manifest.json"
    passes_manifest = {}
    if passes_manifest_path.exists():
        passes_manifest = json.loads(passes_manifest_path.read_text(encoding="utf-8"))
    return {
        "doc_id": doc_id,
        "manifest": manifest,
        "passes": passes_manifest.get("passes", {}),
    }


@router.get("/results/{doc_id}", response_model=dict)
async def results(doc_id: str) -> dict[str, Any]:
    """Return artifact manifest for given document."""

    settings = get_settings()
    doc_root = Path(settings.artifact_root_path) / doc_id
    manifest_path = doc_root / "passes" / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="pass manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    passes: dict[str, Any] = {}
    for name, path in manifest.get("passes", {}).items():
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = doc_root / "passes" / candidate.name
        if not candidate.exists():
            logger.warning("pipeline.results.missing", extra={"path": str(candidate)})
            continue
        passes[name] = json.loads(candidate.read_text(encoding="utf-8"))
    return {"doc_id": doc_id, "passes": passes}


@router.get("/artifacts")
async def stream_artifact(path: str) -> StreamingResponse:
    """Stream artifact bytes to client using chunked transfer."""

    settings = get_settings()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path(settings.artifact_root_path) / path
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    iterator = stream_read(str(candidate))
    return StreamingResponse(iterator, media_type="application/octet-stream")


__all__ = ["PipelineRunRequest", "run_pipeline", "status", "results", "stream_artifact"]
