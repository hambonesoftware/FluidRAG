"""Produce a lightweight normalized artifact for PDF uploads."""

from __future__ import annotations

import re
from typing import Any

from .....util.audit import stage_record
from .....util.logging import get_logger

logger = get_logger(__name__)

_IMAGE_PATTERN = re.compile(r"\[image:(?P<name>[^\]]+)\]", re.IGNORECASE)


def _decode_source_text(payload: bytes, fallback: str | None = None) -> str:
    if payload:
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError:
            return payload.decode("latin-1", errors="ignore")
    if fallback:
        return fallback
    return ""


def _split_pages(text: str) -> list[str]:
    if not text:
        return [""]
    normalized = text.replace("\r\n", "\n")
    pages = [segment.strip() for segment in normalized.split("\f")]
    if len(pages) == 1:
        # treat double blank lines as page separators when no form feed exists
        candidates = [segment.strip() for segment in normalized.split("\n\n\n")]
        if len(candidates) > 1:
            pages = candidates
    return pages or [""]


def _split_blocks(page_text: str) -> list[str]:
    if not page_text:
        return []
    parts: list[str] = []
    for segment in re.split(r"\n{2,}", page_text.strip()):
        cleaned = segment.strip()
        if cleaned:
            parts.append(cleaned)
    if not parts and page_text.strip():
        parts.append(page_text.strip())
    return parts


def _infer_font(text: str) -> dict[str, Any]:
    length = len(text)
    upper_ratio = sum(1 for c in text if c.isupper()) / max(length, 1)
    is_heading = upper_ratio > 0.6 and length < 80
    return {
        "family": "SourceSerif" if is_heading else "SourceSans",
        "size": 18 if is_heading else 12,
        "weight": "bold" if is_heading else "normal",
        "style": "normal",
    }


def normalize_pdf(
    doc_id: str,
    *,
    file_id: str | None = None,
    file_name: str | None = None,
    source_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Extract text/layout/style into a normalized JSON."""
    payload = source_bytes or b""
    source_text = _decode_source_text(payload, fallback=file_id)
    pages_raw = _split_pages(source_text)

    normalized: dict[str, Any] = {
        "doc_id": doc_id,
        "source": {"file_id": file_id, "file_name": file_name},
        "pages": [],
        "stats": {
            "page_count": len(pages_raw),
            "block_count": 0,
            "avg_coverage": 0.0,
            "images": 0,
            "source_bytes": len(payload),
        },
        "audit": [
            stage_record(
                stage="normalize.load",
                status="ok",
                chars=len(source_text),
                bytes=len(payload),
            ),
        ],
    }

    coverages: list[float] = []
    total_blocks = 0
    for page_number, page_text in enumerate(pages_raw, start=1):
        blocks: list[dict[str, Any]] = []
        images: list[dict[str, Any]] = []
        for match in _IMAGE_PATTERN.finditer(page_text):
            images.append(
                {
                    "id": f"{doc_id}:p{page_number}:img{len(images) + 1}",
                    "description": match.group("name").strip(),
                }
            )
        cleaned_page_text = _IMAGE_PATTERN.sub("", page_text)
        for block_index, block in enumerate(_split_blocks(cleaned_page_text), start=1):
            block_id = f"{doc_id}:p{page_number}:b{block_index}"
            blocks.append(
                {
                    "id": block_id,
                    "page": page_number,
                    "text": block,
                    "bbox": [0.0, 0.0, 1.0, 1.0],
                    "font": _infer_font(block),
                    "confidence": 1.0,
                }
            )
        coverage = 1.0 if blocks else 0.0
        coverages.append(coverage)
        total_blocks += len(blocks)
        normalized["pages"].append(
            {
                "page_number": page_number,
                "text": cleaned_page_text.strip(),
                "blocks": blocks,
                "images": images,
                "coverage": coverage,
            }
        )

    normalized["stats"]["block_count"] = total_blocks
    normalized["stats"]["images"] = sum(
        len(page["images"]) for page in normalized["pages"]
    )
    normalized["stats"]["avg_coverage"] = (
        sum(coverages) / len(coverages) if coverages else 0.0
    )
    normalized["audit"].append(
        stage_record(
            stage="normalize.summary",
            status="ok",
            pages=len(pages_raw),
            blocks=total_blocks,
            avg_coverage=normalized["stats"]["avg_coverage"],
        )
    )
    logger.debug(
        "upload.normalize_pdf",
        extra={
            "doc_id": doc_id,
            "pages": len(pages_raw),
            "blocks": total_blocks,
            "avg_coverage": normalized["stats"]["avg_coverage"],
        },
    )
    return normalized
