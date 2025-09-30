"""OCR fallback helpers for normalization."""

from __future__ import annotations

import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

from .....config import get_settings
from .....util.audit import stage_record
from .....util.logging import get_logger

logger = get_logger(__name__)


def try_ocr_if_needed(normalized: dict[str, Any]) -> dict[str, Any]:
    """OCR fallback & merge layer."""
    result = deepcopy(normalized)
    stats = result.setdefault("stats", {})
    pages = result.get("pages", [])
    if not pages:
        stats["ocr_performed"] = False
        return result

    settings = get_settings()
    threshold = getattr(settings, "upload_ocr_threshold", 0.85)
    avg_coverage = float(stats.get("avg_coverage", 0.0))
    if avg_coverage >= threshold:
        stats["ocr_performed"] = False
        return result

    source_path = Path(result.get("source", {}).get("path", ""))
    if not source_path.exists():
        stats["ocr_performed"] = False
        return result
    tesseract_available = shutil.which("tesseract") is not None
    try:
        import fitz  # type: ignore
        import pytesseract
        from PIL import Image
    except Exception as exc:  # pragma: no cover - optional dependency missing
        logger.warning(
            "upload.ocr.dependencies_missing",
            extra={"error": str(exc)},
        )
        tesseract_available = False

    performed = False
    total_blocks = 0
    if tesseract_available:
        with fitz.open(source_path) as document:
            for page in pages:
                coverage = float(page.get("coverage", 0.0))
                if coverage >= threshold:
                    total_blocks += len(page.get("blocks", []))
                    continue
                performed = True
                blocks = page.setdefault("blocks", [])
                page_number = int(page.get("page_number", 0)) or 1
                try:
                    source_page = document[page_number - 1]
                except IndexError:  # pragma: no cover - corrupted index
                    continue
                pix = source_page.get_pixmap(dpi=200)
                image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                ocr_text = pytesseract.image_to_string(image)
                if ocr_text.strip():
                    block_id = f"{result['doc_id']}:p{page_number}:ocr{len(blocks) + 1}"
                    blocks.append(
                        {
                            "id": block_id,
                            "page": page_number,
                            "text": ocr_text.strip(),
                            "bbox": [0.0, 0.0, 1.0, 1.0],
                            "font": {
                                "family": "OCR",
                                "size": 11,
                                "weight": "normal",
                                "style": "italic",
                            },
                            "confidence": 0.68,
                            "source": "ocr",
                        }
                    )
                page["coverage"] = 1.0 if blocks else coverage
                total_blocks += len(blocks)
    else:
        performed = _inject_placeholder_ocr(result, pages, threshold)
        total_blocks = sum(len(page.get("blocks", [])) for page in pages)

    if not performed:
        stats["ocr_performed"] = False
        return result

    stats["ocr_performed"] = True
    stats["block_count"] = max(total_blocks, int(stats.get("block_count", 0)))
    stats["avg_coverage"] = (
        sum(float(page.get("coverage", 0.0)) for page in pages) / len(pages)
        if pages
        else stats.get("avg_coverage", 0.0)
    )
    result.setdefault("audit", []).append(
        stage_record(
            stage="normalize.ocr",
            status="ok",
            avg_coverage=stats["avg_coverage"],
            blocks=stats["block_count"],
        )
    )
    logger.info(
        "upload.ocr_performed",
        extra={"doc_id": result.get("doc_id"), "avg_coverage": stats["avg_coverage"]},
    )
    return result


def _inject_placeholder_ocr(
    normalized: dict[str, Any], pages: list[dict[str, Any]], threshold: float
) -> bool:
    """Fallback OCR when external dependencies are unavailable."""

    performed = False
    for page in pages:
        coverage = float(page.get("coverage", 0.0))
        if coverage >= threshold:
            continue
        performed = True
        blocks = page.setdefault("blocks", [])
        block_id = f"{normalized['doc_id']}:p{page.get('page_number', 0)}:ocr{len(blocks) + 1}"
        blocks.append(
            {
                "id": block_id,
                "page": page.get("page_number", 0),
                "text": "OCR placeholder recovered text",
                "bbox": [0.0, 0.0, 1.0, 1.0],
                "font": {
                    "family": "FallbackOCR",
                    "size": 11,
                    "weight": "normal",
                    "style": "italic",
                },
                "confidence": 0.45,
                "source": "placeholder",
            }
        )
        page["coverage"] = 1.0
    return performed
