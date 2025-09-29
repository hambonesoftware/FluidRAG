"""Controller orchestrating retrieval passes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

from backend.app.adapters import LLMClient, read_jsonl, write_json
from backend.app.config import get_settings
from backend.app.contracts.passes import PassManifest
from backend.app.util.audit import stage_record
from backend.app.util.errors import AppError, NotFoundError, ValidationError
from backend.app.util.logging import get_logger

from .packages.compose.context import compose_window
from .packages.emit.results import write_pass_results
from .packages.prompts import (
    ControlsPrompt,
    ElectricalPrompt,
    MechanicalPrompt,
    ProjectManagementPrompt,
    SoftwarePrompt,
)
from .packages.retrieval import retrieve_ranked

logger = get_logger(__name__)


class PromptTemplate(Protocol):
    """Protocol describing prompt renderers."""

    def render(self, context: str) -> tuple[str, str]:
        ...


class PassJobsInternal(BaseModel):
    """Internal pass job bundle."""

    doc_id: str
    manifest_path: str
    passes: dict[str, str]


def _validate_inputs(doc_id: str, rechunk_artifact: str) -> Path:
    if not doc_id or not doc_id.strip():
        raise ValidationError("doc_id is required for pass execution")
    path = Path(rechunk_artifact)
    if not path.exists():
        raise NotFoundError(f"header chunks artifact missing: {rechunk_artifact}")
    return path


def _load_chunks(path: Path) -> list[dict[str, Any]]:
    chunks = read_jsonl(str(path))
    if not chunks:
        raise ValidationError("header chunks artifact empty")
    for index, chunk in enumerate(chunks):
        chunk.setdefault("chunk_id", chunk.get("id") or f"{index}")
        chunk.setdefault("header_path", chunk.get("header_path") or chunk.get("header"))
        chunk.setdefault("sentence_start", chunk.get("sentence_start", 0))
        chunk.setdefault("sentence_end", chunk.get("sentence_end", 0))
    return chunks


def run_all(doc_id: str, rechunk_artifact: str) -> PassJobsInternal:
    """Retrieve, compose context, LLM calls, emit results."""

    path = _validate_inputs(doc_id, rechunk_artifact)
    try:
        settings = get_settings()
        chunks = _load_chunks(path)
        prompts: dict[str, PromptTemplate] = {
            "mechanical": MechanicalPrompt(),
            "electrical": ElectricalPrompt(),
            "software": SoftwarePrompt(),
            "controls": ControlsPrompt(),
            "project_mgmt": ProjectManagementPrompt(),
        }
        llm = LLMClient()
        manifests: dict[str, str] = {}
        for name, prompt in prompts.items():
            ranked = retrieve_ranked(chunks, domain=name)
            context = compose_window(ranked, budget_tokens=400)
            system, user = prompt.render(context)
            completion = llm.chat(system=system, user=user, context=context)
            completion["context"] = context
            completion["prompt"] = {"system": system, "user": user}
            artifact = write_pass_results(doc_id, name, completion, ranked)
            manifests[name] = artifact

        manifest_path = (
            Path(settings.artifact_root_path) / doc_id / "passes" / "manifest.json"
        )
        payload = PassManifest(doc_id=doc_id, passes=manifests)
        write_json(str(manifest_path), payload.model_dump())

        logger.info(
            "passes.run_all.success",
            extra={"doc_id": doc_id, "passes": len(manifests)},
        )

        audit_path = manifest_path.with_name("passes.audit.json")
        audit_payload = stage_record(
            stage="passes.run_all",
            status="ok",
            doc_id=doc_id,
            passes=len(manifests),
        )
        write_json(str(audit_path), audit_payload)

        return PassJobsInternal(
            doc_id=doc_id,
            manifest_path=str(manifest_path),
            passes=manifests,
        )
    except Exception as exc:  # noqa: BLE001
        handle_pass_errors(exc)
        raise


def handle_pass_errors(e: Exception) -> None:
    """Normalize and raise rag pass errors."""

    if isinstance(e, ValidationError):
        logger.warning("passes.validation_failed", extra={"error": str(e)})
        raise
    if isinstance(e, NotFoundError):
        logger.error("passes.artifact_missing", extra={"error": str(e)})
        raise
    if isinstance(e, AppError):
        raise
    logger.error("passes.unexpected", extra={"error": str(e), "type": type(e).__name__})
    raise AppError("pass execution failed") from e


__all__ = ["PassJobsInternal", "run_all", "handle_pass_errors"]
