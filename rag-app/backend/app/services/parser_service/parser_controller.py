"""Parser controller orchestrating fan-out/fan-in."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ...config import get_settings
from ...util.audit import stage_record
from ...util.errors import AppError, NotFoundError, ValidationError
from ...util.logging import get_logger
from .packages.detect.language import detect_language
from .packages.enhance.lists_bullets import detect_lists_bullets
from .packages.enhance.reading_order import build_reading_order
from .packages.enhance.semantics import infer_semantics
from .packages.extract.images import extract_images
from .packages.extract.links import extract_links
from .packages.extract.pdf_text import extract_text_blocks
from .packages.extract.tables import extract_tables
from .packages.merge.merger import merge_all
from .packages.ocr.ocr_router import maybe_ocr

logger = get_logger(__name__)


class ParseInternal(BaseModel):
    """Internal parsed artifact descriptor."""

    doc_id: str
    enriched_path: str
    language: str
    summary: dict[str, Any]
    metrics: dict[str, float]


async def _fan_out(
    normalized: dict[str, Any],
    normalize_path: Path,
    timeout: float,
) -> tuple[dict[str, Any], dict[str, float]]:
    async def run(name: str, func, *args) -> tuple[str, Any, float]:
        start = time.perf_counter()
        result = await asyncio.wait_for(asyncio.to_thread(func, *args), timeout=timeout)
        return name, result, time.perf_counter() - start

    tasks = {
        "text": asyncio.create_task(run("text", extract_text_blocks, normalized)),
        "tables": asyncio.create_task(run("tables", extract_tables, normalized)),
        "images": asyncio.create_task(run("images", extract_images, normalized)),
        "links": asyncio.create_task(run("links", extract_links, normalized)),
        "language": asyncio.create_task(
            run("language", detect_language, normalized.get("pages", []))
        ),
    }
    results: dict[str, Any] = {}
    metrics: dict[str, float] = {}
    try:
        for task in tasks.values():
            key, value, duration = await task
            results[key] = value
            metrics[key] = duration
    except Exception:
        for task in tasks.values():
            task.cancel()
        raise

    text_blocks = results.get("text", [])
    ocr_name, ocr_result, ocr_duration = await run(
        "ocr", maybe_ocr, str(normalize_path), text_blocks
    )
    metrics[ocr_name] = ocr_duration
    results[ocr_name] = ocr_result

    order_name, reading_order, reading_duration = await run(
        "reading_order",
        build_reading_order,
        text_blocks,
        ocr_result,
        results.get("images", []),
    )
    metrics[order_name] = reading_duration
    results[order_name] = reading_order

    semantics_name, semantics, semantics_duration = await run(
        "semantics",
        infer_semantics,
        text_blocks,
        results.get("tables", []),
        results.get("images", []),
    )
    metrics[semantics_name] = semantics_duration
    results[semantics_name] = semantics

    lists_name, lists_result, lists_duration = await run(
        "lists", detect_lists_bullets, text_blocks
    )
    metrics[lists_name] = lists_duration
    results[lists_name] = lists_result
    return results, metrics


def parse_and_enrich(doc_id: str, normalize_artifact: str) -> ParseInternal:
    """Controller: async fan-out of parse subtasks; fan-in, merge, write JSON."""
    settings = get_settings()
    normalize_path = Path(normalize_artifact)
    if not normalize_path.exists():
        handle_parser_errors(FileNotFoundError(normalize_artifact))
    try:
        normalized = json.loads(normalize_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        handle_parser_errors(exc)

    timeout = getattr(settings, "parser_timeout_seconds", 1.0)
    try:
        results, metrics = asyncio.run(
            _fan_out(
                normalized=normalized, normalize_path=normalize_path, timeout=timeout
            )
        )
    except Exception as exc:  # noqa: BLE001
        handle_parser_errors(exc)
        raise  # pragma: no cover

    language = results.get("language", {"code": "und"})
    enriched = merge_all(
        doc_id=doc_id,
        language=language,
        text_blocks=results.get("text", []),
        tables=results.get("tables", []),
        images=results.get("images", []),
        links=results.get("links", []),
        ocr_layer=results.get("ocr", {}),
        reading_order=results.get("reading_order", []),
        semantics=results.get("semantics", []),
        lists=results.get("lists", []),
    )

    artifact_root = Path(settings.artifact_root_path) / doc_id
    artifact_root.mkdir(parents=True, exist_ok=True)
    enriched_path = artifact_root / "parse.enriched.json"
    enriched.setdefault("audit", []).append(
        stage_record(stage="parser.merge", status="ok", doc_id=doc_id)
    )
    enriched_path.write_text(
        json.dumps(enriched, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info(
        "parser.parse_and_enrich.success",
        extra={
            "doc_id": doc_id,
            "language": language.get("code"),
            "blocks": len(enriched.get("blocks", [])),
            "tables": len(enriched.get("tables", [])),
        },
    )
    return ParseInternal(
        doc_id=doc_id,
        enriched_path=str(enriched_path),
        language=language.get("code", "und"),
        summary=enriched.get("summary", {}),
        metrics=metrics,
    )


def handle_parser_errors(e: Exception) -> None:
    """Normalize and raise parser errors."""
    if isinstance(e, ValidationError):
        logger.warning("parser.validation_failed", extra={"error": str(e)})
        raise
    if isinstance(e, FileNotFoundError):
        logger.error("parser.normalize_missing", extra={"error": str(e)})
        raise NotFoundError(str(e)) from e
    if isinstance(e, AppError):
        raise
    logger.error("parser.unexpected", extra={"error": str(e), "type": type(e).__name__})
    raise AppError("parser enrichment failed") from e
