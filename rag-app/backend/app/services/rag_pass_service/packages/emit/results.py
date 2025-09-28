"""Emitter utilities for pass results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app.adapters.storage import write_json
from backend.app.config import get_settings
from backend.app.contracts.ids import make_pass_id, pass_artifact_name
from backend.app.contracts.passes import (
    Citation,
    PassManifest,
    PassResult,
    RetrievalTrace,
)
from backend.app.util.logging import get_logger

logger = get_logger(__name__)


def write_pass_results(
    doc_id: str, pass_name: str, answer: Any, ranked: list[dict[str, Any]]
) -> str:
    """Persist pass outputs with retrieval debug."""

    settings = get_settings()
    passes_dir = Path(settings.artifact_root_path) / doc_id / "passes"
    passes_dir.mkdir(parents=True, exist_ok=True)

    pass_id = make_pass_id(doc_id, pass_name)
    artifact_path = passes_dir / pass_artifact_name(pass_name)

    citations = [
        Citation(
            chunk_id=str(item.get("chunk_id")),
            header_path=item.get("header_path") or item.get("header"),
            sentence_start=item.get("sentence_start"),
            sentence_end=item.get("sentence_end"),
        )
        for item in ranked[:3]
        if item.get("chunk_id")
    ]
    retrieval = [
        RetrievalTrace(
            chunk_id=str(item.get("chunk_id")),
            header_path=item.get("header_path") or item.get("header"),
            score=float(item.get("score", 0.0)),
            dense_score=float(item.get("dense_score", 0.0)),
            sparse_score=float(item.get("sparse_score", 0.0)),
            flow_score=float(item.get("flow_score", 0.0)),
            energy_score=float(item.get("energy_score", 0.0)),
            graph_score=float(item.get("graph_score", 0.0)),
            text_preview=str(item.get("text", ""))[:256],
        )
        for item in ranked
        if item.get("chunk_id")
    ]

    prompt_payload: dict[str, Any] = {}
    if isinstance(answer, dict) and "prompt" in answer:
        prompt_payload = dict(answer.get("prompt") or {})

    answer_text = answer
    if isinstance(answer, dict):
        answer_text = answer.get("content") or answer.get("answer") or ""

    result = PassResult(
        doc_id=doc_id,
        pass_id=pass_id,
        pass_name=pass_name,
        answer=str(answer_text).strip(),
        citations=citations,
        retrieval=retrieval,
        context=str(answer.get("context")) if isinstance(answer, dict) else "",
        prompt=prompt_payload,
    )
    write_json(str(artifact_path), result.model_dump())

    manifest_path = passes_dir / "manifest.json"
    manifest = PassManifest(doc_id=doc_id, passes={})
    if manifest_path.exists():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = PassManifest(**payload)
        except Exception:  # noqa: BLE001
            logger.warning(
                "passes.manifest_corrupt", extra={"path": str(manifest_path)}
            )
    manifest.passes[pass_name] = str(artifact_path)
    write_json(str(manifest_path), manifest.model_dump())

    logger.info(
        "passes.emit.success",
        extra={"doc_id": doc_id, "pass": pass_name, "path": str(artifact_path)},
    )
    return str(artifact_path)


__all__ = ["write_pass_results"]
