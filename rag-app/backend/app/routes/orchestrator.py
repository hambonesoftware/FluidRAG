"""Pipeline orchestrator routes."""
from __future__ import annotations

import base64
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.app.adapters.storage import storage
from backend.app.services.chunk_service import run_uf_chunking
from backend.app.services.header_service import join_and_rechunk
from backend.app.services.parser_service import parse_and_enrich
from backend.app.services.rag_pass_service import run_all
from backend.app.services.upload_service import ensure_normalized
from backend.app.util.errors import AppError

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])

_PIPELINE_STATUS: Dict[str, str] = {}


class PipelineRunRequest(BaseModel):
    file_name: str
    content: str
    content_type: str = "application/pdf"


@router.post("/run")
def run_pipeline(payload: PipelineRunRequest) -> Any:
    try:
        raw = base64.b64decode(payload.content.encode("utf-8"))
        normalized = ensure_normalized(
            file_name=payload.file_name,
            content=raw,
            content_type=payload.content_type,
        )
        _PIPELINE_STATUS[normalized.doc_id] = "uploaded"

        parse_and_enrich(normalized.to_contract())
        _PIPELINE_STATUS[normalized.doc_id] = "parsed"

        run_uf_chunking(doc_id=normalized.doc_id, normalize_artifact=normalized.manifest_path)
        _PIPELINE_STATUS[normalized.doc_id] = "chunked"

        chunks_artifact = str(Path(normalized.manifest_path).parent / "chunks.jsonl")
        join_and_rechunk(doc_id=normalized.doc_id, chunks_artifact=chunks_artifact)
        _PIPELINE_STATUS[normalized.doc_id] = "headers"

        rechunk_artifact = str(Path(chunks_artifact).parent / "headers.json")
        passes_result = run_all(doc_id=normalized.doc_id, rechunk_artifact=rechunk_artifact)
        _PIPELINE_STATUS[normalized.doc_id] = "passes"

        pipeline_summary = {
            "doc_id": normalized.doc_id,
            "manifest": normalized.manifest_path,
            "chunks_artifact": chunks_artifact,
            "rechunk_artifact": rechunk_artifact,
            "passes": [asdict(pass_result) for pass_result in passes_result.passes],
        }
        storage.write_json(f"{normalized.doc_id}/pipeline.json", pipeline_summary)
        _PIPELINE_STATUS[normalized.doc_id] = "complete"
        return pipeline_summary
    except Exception as exc:
        if isinstance(exc, AppError):
            raise HTTPException(status_code=400, detail=exc.to_dict())
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{doc_id}/status")
def status(doc_id: str) -> Dict[str, str]:
    state = _PIPELINE_STATUS.get(doc_id, "unknown")
    return {"doc_id": doc_id, "status": state}


@router.get("/{doc_id}/results")
def results(doc_id: str) -> Any:
    pipeline_path = Path(storage.base_dir) / doc_id / "pipeline.json"
    if not pipeline_path.exists():
        raise HTTPException(status_code=404, detail="Results not found")
    return json.loads(pipeline_path.read_text(encoding="utf-8"))


@router.get("/artifact")
def stream_artifact(path: str) -> FileResponse:
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(file_path)
