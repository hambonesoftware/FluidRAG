"""Parser controller orchestrating fan-out/fan-in."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ...config import get_settings
from ...util.audit import stage_record
from ...util.errors import AppError, NotFoundError, ValidationError
from ...util.logging import get_logger, log_span
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


def _fan_out(
    normalized: dict[str, Any],
    normalize_path: Path,
) -> tuple[dict[str, Any], dict[str, float]]:
    """Run parser fan-out sequentially with timing metrics."""

    metrics: dict[str, float] = {}

    def timed(name: str, func: Any, *args: Any) -> Any:
        start = time.perf_counter()
        value = func(*args)
        metrics[name] = time.perf_counter() - start
        return value

    text_blocks = timed("text", extract_text_blocks, normalized)
    tables = timed("tables", extract_tables, normalized)
    images = timed("images", extract_images, normalized)
    links = timed("links", extract_links, normalized)
    language = timed("language", detect_language, normalized.get("pages", []))
    ocr_result = timed("ocr", maybe_ocr, str(normalize_path), text_blocks)
    reading_order = timed(
        "reading_order",
        build_reading_order,
        text_blocks,
        ocr_result,
        images,
    )
    semantics = timed("semantics", infer_semantics, text_blocks, tables, images)
    lists_result = timed("lists", detect_lists_bullets, text_blocks)

    results = {
        "text": text_blocks,
        "tables": tables,
        "images": images,
        "links": links,
        "language": language,
        "ocr": ocr_result,
        "reading_order": reading_order,
        "semantics": semantics,
        "lists": lists_result,
    }
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
    controller_start = time.perf_counter()
    try:
        with log_span(
            "parser.parse_and_enrich",
            logger=logger,
            extra={"doc_id": doc_id, "timeout": timeout},
        ) as span_meta:
            results, metrics = _fan_out(
                normalized=normalized,
                normalize_path=normalize_path,
            )
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
            span_meta["language"] = language.get("code", "und")
            span_meta["blocks"] = len(enriched.get("blocks", []))
    except Exception as exc:  # noqa: BLE001
        handle_parser_errors(exc)
        raise  # pragma: no cover

    artifact_root = Path(settings.artifact_root_path) / doc_id
    artifact_root.mkdir(parents=True, exist_ok=True)
    enriched_path = artifact_root / "parse.enriched.json"
    duration_ms = (time.perf_counter() - controller_start) * 1000.0
    enriched.setdefault("audit", []).append(
        stage_record(
            stage="parser.merge",
            status="ok",
            doc_id=doc_id,
            duration_ms=duration_ms,
            blocks=len(enriched.get("blocks", [])),
        )
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
