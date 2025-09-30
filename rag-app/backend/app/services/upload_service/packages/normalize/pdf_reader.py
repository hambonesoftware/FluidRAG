"""Produce a normalized artifact for PDF uploads."""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

from .....util.audit import stage_record
from .....util.logging import get_logger

logger = get_logger(__name__)

_PLAIN_IMAGE_PATTERN = re.compile(r"\[image:(?P<name>[^\]]+)\]", re.IGNORECASE)


def normalize_pdf(
    *,
    doc_id: str,
    source_path: str | Path,
    source_sha256: str,
    original_filename: str | None,
    content_type: str | None,
    size_bytes: int,
) -> dict[str, Any]:
    """Extract text, layout, and style metadata into a normalized JSON payload."""

    path = Path(source_path)
    normalized: dict[str, Any] = {
        "doc_id": doc_id,
        "source": {
            "path": str(path),
            "file_name": original_filename,
            "content_type": content_type,
            "sha256": source_sha256,
            "size_bytes": size_bytes,
        },
        "pages": [],
        "stats": {
            "page_count": 0,
            "block_count": 0,
            "avg_coverage": 0.0,
            "images": 0,
            "ocr_performed": False,
        },
        "audit": [
            stage_record(
                stage="normalize.load",
                status="ok",
                path=str(path),
                size_bytes=size_bytes,
            )
        ],
    }

    try:
        import fitz  # type: ignore

        normalized = _normalize_with_pymupdf(
            doc_id=doc_id,
            path=path,
            normalized=normalized,
        )
    except Exception as exc:  # pragma: no cover - dependency/format fallback
        logger.warning(
            "upload.normalize_pdf.fallback",
            extra={"doc_id": doc_id, "error": str(exc)},
        )
        normalized = _normalize_plaintext(path, normalized)

    stats = normalized.setdefault("stats", {})
    pages = normalized.get("pages", [])
    stats["page_count"] = len(pages)
    stats.setdefault("block_count", sum(len(page.get("blocks", [])) for page in pages))
    stats.setdefault("images", sum(len(page.get("images", [])) for page in pages))
    if pages and "avg_coverage" not in stats:
        stats["avg_coverage"] = round(
            sum(float(page.get("coverage", 0.0)) for page in pages) / len(pages), 4
        )
    normalized.setdefault("audit", []).append(
        stage_record(
            stage="normalize.summary",
            status="ok",
            pages=stats.get("page_count", 0),
            blocks=stats.get("block_count", 0),
            avg_coverage=stats.get("avg_coverage", 0.0),
        )
    )
    logger.debug(
        "upload.normalize_pdf",
        extra={
            "doc_id": doc_id,
            "pages": stats.get("page_count", 0),
            "blocks": stats.get("block_count", 0),
            "avg_coverage": stats.get("avg_coverage", 0.0),
        },
    )
    return normalized


def _normalize_with_pymupdf(
    *, doc_id: str, path: Path, normalized: dict[str, Any]
) -> dict[str, Any]:
    import fitz  # type: ignore

    pages: list[dict[str, Any]] = []
    total_block_area = 0.0
    total_page_area = 0.0
    total_blocks = 0
    total_images = 0

    with fitz.open(path) as document:
        for index, page in enumerate(document, start=1):
            page_dict = page.get_text("dict")
            text_blocks: list[dict[str, Any]] = []
            block_area_sum = 0.0
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                text = _collect_block_text(block)
                if not text.strip():
                    continue
                spans = [
                    span
                    for line in block.get("lines", [])
                    for span in line.get("spans", [])
                    if span.get("text", "").strip()
                ]
                bbox = block.get("bbox", [0.0, 0.0, 0.0, 0.0])
                block_area_sum += _area(bbox)
                text_blocks.append(
                    {
                        "id": f"{doc_id}:p{index}:b{len(text_blocks) + 1}",
                        "page": index,
                        "text": text,
                        "bbox": _normalize_bbox(bbox, page.rect),
                        "font": _style_from_spans(spans),
                        "confidence": _confidence_from_spans(spans),
                    }
                )

            page_area = max(page.rect.width * page.rect.height, 1.0)
            coverage = min(1.0, block_area_sum / page_area)
            total_block_area += block_area_sum
            total_page_area += page_area
            total_blocks += len(text_blocks)

            images = _extract_images(doc_id, index, page)
            total_images += len(images)

            pages.append(
                {
                    "page_number": index,
                    "text": page.get_text("text").strip(),
                    "blocks": text_blocks,
                    "images": images,
                    "coverage": round(coverage, 4),
                }
            )

    normalized["pages"] = pages
    normalized.setdefault("stats", {})
    normalized["stats"]["block_count"] = total_blocks
    normalized["stats"]["images"] = total_images
    normalized["stats"]["avg_coverage"] = (
        round(total_block_area / total_page_area, 4) if total_page_area else 0.0
    )
    return normalized


def _normalize_plaintext(path: Path, normalized: dict[str, Any]) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    pages = [segment.strip() for segment in text.split("\f") if segment.strip()]
    if not pages:
        pages = [text.strip()]
    pages = [page for page in pages if page]
    if not pages:
        pages = [""]

    normalized_pages: list[dict[str, Any]] = []
    total_blocks = 0
    for index, content in enumerate(pages, start=1):
        blocks = [
            {
                "id": f"{normalized['doc_id']}:p{index}:b{block_index}",
                "page": index,
                "text": block,
                "bbox": [0.0, 0.0, 1.0, 1.0],
                "font": _fallback_font(block),
                "confidence": 0.75,
            }
            for block_index, block in enumerate(_split_plain_blocks(content), start=1)
        ]
        total_blocks += len(blocks)
        normalized_pages.append(
            {
                "page_number": index,
                "text": content,
                "blocks": blocks,
                "images": _extract_plain_images(content, normalized["doc_id"], index),
                "coverage": 1.0 if blocks else 0.0,
            }
        )

    normalized["pages"] = normalized_pages
    normalized.setdefault("stats", {})
    normalized["stats"]["block_count"] = total_blocks
    normalized["stats"]["images"] = sum(
        len(page.get("images", [])) for page in normalized_pages
    )
    normalized["stats"]["avg_coverage"] = (
        sum(page.get("coverage", 0.0) for page in normalized_pages) / len(normalized_pages)
        if normalized_pages
        else 0.0
    )
    return normalized


def _collect_block_text(block: dict[str, Any]) -> str:
    texts: list[str] = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            texts.append(span.get("text", ""))
        texts.append("\n")
    return "".join(texts).strip()


def _style_from_spans(spans: list[dict[str, Any]]) -> dict[str, Any]:
    if not spans:
        return {
            "family": "Unknown",
            "size": 0.0,
            "weight": "normal",
            "style": "normal",
        }
    primary = max(spans, key=lambda span: span.get("size", 0.0))
    weight = "bold" if primary.get("flags", 0) & 2 else "normal"
    style = "italic" if primary.get("flags", 0) & 1 else "normal"
    return {
        "family": primary.get("font", "Unknown"),
        "size": round(float(primary.get("size", 0.0)), 2),
        "weight": weight,
        "style": style,
    }


def _confidence_from_spans(spans: list[dict[str, Any]]) -> float:
    if not spans:
        return 0.75
    confidences = [float(span.get("confidence", 0.95)) for span in spans]
    return round(sum(confidences) / len(confidences), 3)


def _extract_images(doc_id: str, page_number: int, page: Any) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    for index, image in enumerate(page.get_images(full=True), start=1):
        xref = image[0]
        width = image[2]
        height = image[3]
        images.append(
            {
                "id": f"{doc_id}:p{page_number}:img{index}",
                "page": page_number,
                "xref": xref,
                "width": width,
                "height": height,
            }
        )
    return images


def _normalize_bbox(bbox: list[float], rect: Any) -> list[float]:
    width = rect.width or 1.0
    height = rect.height or 1.0
    x0, y0, x1, y1 = bbox
    return [
        round(float(x0) / width, 4),
        round(float(y0) / height, 4),
        round(float(x1) / width, 4),
        round(float(y1) / height, 4),
    ]


def _area(bbox: list[float]) -> float:
    if len(bbox) != 4:
        return 0.0
    x0, y0, x1, y1 = bbox
    return max((x1 - x0) * (y1 - y0), 0.0)


def _split_plain_blocks(content: str) -> list[str]:
    segments = [segment.strip() for segment in re.split(r"\n{2,}", content)]
    return [segment for segment in segments if segment]


def _fallback_font(block: str) -> dict[str, Any]:
    is_heading = bool(block.strip()) and len(block) < 80 and block.isupper()
    return {
        "family": "Fallback",
        "size": 16 if is_heading else 12,
        "weight": "bold" if is_heading else "normal",
        "style": "normal",
    }


def _extract_plain_images(content: str, doc_id: str, page_number: int) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    for match in _PLAIN_IMAGE_PATTERN.finditer(content):
        images.append(
            {
                "id": f"{doc_id}:p{page_number}:img{len(images) + 1}",
                "page": page_number,
                "description": match.group("name").strip(),
            }
        )
    return images
