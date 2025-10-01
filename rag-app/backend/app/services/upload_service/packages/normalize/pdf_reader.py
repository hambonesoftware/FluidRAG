"""Produce a lightweight normalized artifact for PDF uploads."""

from __future__ import annotations

import contextlib
import io
import re
import statistics
from collections import Counter
from typing import Any, Callable, Iterable

from .....util.audit import stage_record
from .....util.logging import get_logger

logger = get_logger(__name__)

_IMAGE_PATTERN = re.compile(r"\[image:(?P<name>[^\]]+)\]", re.IGNORECASE)


def _rounded_bbox(bbox: Iterable[float]) -> list[float]:
    return [round(float(coord), 3) for coord in bbox]


def _font_from_spans(spans: list[dict[str, Any]]) -> dict[str, Any]:
    if not spans:
        return {"family": "Unknown", "size": 12.0, "weight": "normal", "style": "normal"}
    fonts = [span.get("font", "") for span in spans if span.get("font")]
    font_family = fonts[0] if not fonts else Counter(fonts).most_common(1)[0][0]
    sizes = [float(span.get("size", 0.0)) for span in spans if span.get("size")]
    avg_size = statistics.fmean(sizes) if sizes else 12.0
    font_lower = [font.lower() for font in fonts]
    is_bold = any("bold" in font for font in font_lower)
    is_italic = any(
        token in font
        for font in font_lower
        for token in ("italic", "oblique")
    )
    weight = "bold" if is_bold else "normal"
    style = "italic" if is_italic else "normal"
    return {
        "family": font_family or "Unknown",
        "size": round(avg_size, 2),
        "weight": weight,
        "style": style,
    }


def _pymupdf_extract(payload: bytes, doc_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    import fitz

    document = fitz.open(stream=payload, filetype="pdf")
    pages: list[dict[str, Any]] = []
    block_total = 0
    image_total = 0
    coverages: list[float] = []

    for page_index, page in enumerate(document, start=1):
        page_dict = page.get_text("dict")
        page_blocks: list[dict[str, Any]] = []
        page_images: list[dict[str, Any]] = []
        text_parts: list[str] = []
        text_area = 0.0
        page_area = float(page.rect.width * page.rect.height) or 1.0

        for block in page_dict.get("blocks", []):
            block_type = block.get("type", 0)
            if block_type == 1:
                image_total += 1
                page_images.append(
                    {
                        "id": f"{doc_id}:p{page_index}:img{len(page_images) + 1}",
                        "bbox": _rounded_bbox(block.get("bbox", (0.0, 0.0, 0.0, 0.0))),
                    }
                )
                continue
            if block_type != 0:
                continue
            spans: list[dict[str, Any]] = []
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if text and text.strip():
                        spans.append(span)
            if not spans:
                continue
            block_text_parts = [span.get("text", "").strip() for span in spans]
            block_text = " ".join(filter(None, block_text_parts)).strip()
            if not block_text:
                continue
            bbox = _rounded_bbox(block.get("bbox", (0.0, 0.0, 0.0, 0.0)))
            text_area += max(0.0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
            block_total += 1
            block_payload = {
                "id": f"{doc_id}:p{page_index}:b{len(page_blocks) + 1}",
                "page": page_index,
                "text": block_text,
                "bbox": bbox,
                "font": _font_from_spans(spans),
                "confidence": 1.0,
            }
            page_blocks.append(block_payload)
            text_parts.append(block_text)

        coverage = min(1.0, text_area / page_area)
        coverages.append(coverage)
        pages.append(
            {
                "page_number": page_index,
                "text": "\n".join(text_parts).strip(),
                "blocks": page_blocks,
                "images": page_images,
                "coverage": coverage,
            }
        )

    stats = {
        "page_count": len(pages),
        "block_count": block_total,
        "images": image_total,
        "avg_coverage": (sum(coverages) / len(coverages)) if coverages else 0.0,
    }
    return pages, stats


def _pdfplumber_extract(payload: bytes, doc_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    import pdfplumber

    pages: list[dict[str, Any]] = []
    coverages: list[float] = []
    block_total = 0
    image_total = 0

    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=True) or []
            text = page.extract_text() or ""
            blocks: list[dict[str, Any]] = []
            text_parts: list[str] = []
            text_area = 0.0
            page_area = float(page.width * page.height) or 1.0

            if words:
                line_groups: dict[int, list[dict[str, Any]]] = {}
                for word in words:
                    line_groups.setdefault(int(word.get("top", 0)), []).append(word)
                for line_index, line_words in enumerate(
                    sorted(line_groups.values(), key=lambda grp: grp[0].get("top", 0))
                ):
                    sorted_words = sorted(line_words, key=lambda item: item.get("x0", 0))
                    line_text = " ".join(word.get("text", "") for word in sorted_words).strip()
                    if not line_text:
                        continue
                    bbox = (
                        min(word.get("x0", 0) for word in sorted_words),
                        min(word.get("top", 0) for word in sorted_words),
                        max(word.get("x1", 0) for word in sorted_words),
                        max(word.get("bottom", 0) for word in sorted_words),
                    )
                    text_area += max(0.0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
                    blocks.append(
                        {
                            "id": f"{doc_id}:p{page_index}:b{len(blocks) + 1}",
                            "page": page_index,
                            "text": line_text,
                            "bbox": _rounded_bbox(bbox),
                            "font": {
                                "family": "Unknown",
                                "size": round(float(line_words[0].get("size", 12.0)), 2),
                                "weight": "normal",
                                "style": "normal",
                            },
                            "confidence": 0.9,
                        }
                    )
                    text_parts.append(line_text)
                    block_total += 1
            elif text:
                for part in filter(None, (segment.strip() for segment in text.splitlines())):
                    blocks.append(
                        {
                            "id": f"{doc_id}:p{page_index}:b{len(blocks) + 1}",
                            "page": page_index,
                            "text": part,
                            "bbox": [0.0, 0.0, float(page.width), float(page.height)],
                            "font": {
                                "family": "Unknown",
                                "size": round(float(page.chars[0].get("size", 12.0)) if page.chars else 12.0, 2),
                                "weight": "normal",
                                "style": "normal",
                            },
                            "confidence": 0.8,
                        }
                    )
                    text_parts.append(part)
                    block_total += 1
                    text_area += page.width * page.height

            coverage = min(1.0, text_area / page_area)
            coverages.append(coverage)
            pages.append(
                {
                    "page_number": page_index,
                    "text": "\n".join(text_parts).strip(),
                    "blocks": blocks,
                    "images": [],
                    "coverage": coverage,
                }
            )

    stats = {
        "page_count": len(pages),
        "block_count": block_total,
        "images": image_total,
        "avg_coverage": (sum(coverages) / len(coverages)) if coverages else 0.0,
    }
    return pages, stats


def _pdfminer_extract(payload: bytes, doc_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextBoxHorizontal, LTTextLineHorizontal

    pages: list[dict[str, Any]] = []
    coverages: list[float] = []
    block_total = 0

    for page_index, page_layout in enumerate(extract_pages(io.BytesIO(payload)), start=1):
        page_blocks: list[dict[str, Any]] = []
        text_parts: list[str] = []
        page_area = float(getattr(page_layout, "width", 1.0) * getattr(page_layout, "height", 1.0)) or 1.0
        text_area = 0.0
        for element in page_layout:
            if isinstance(element, (LTTextBoxHorizontal, LTTextLineHorizontal)):
                text = element.get_text().strip()
                if not text:
                    continue
                bbox = (element.x0, element.y0, element.x1, element.y1)
                text_area += max(0.0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
                block_total += 1
                page_blocks.append(
                    {
                        "id": f"{doc_id}:p{page_index}:b{len(page_blocks) + 1}",
                        "page": page_index,
                        "text": text,
                        "bbox": _rounded_bbox(bbox),
                        "font": {
                            "family": "Unknown",
                            "size": 12.0,
                            "weight": "normal",
                            "style": "normal",
                        },
                        "confidence": 0.6,
                    }
                )
                text_parts.append(text)

        coverage = min(1.0, text_area / page_area)
        coverages.append(coverage)
        pages.append(
            {
                "page_number": page_index,
                "text": "\n".join(text_parts).strip(),
                "blocks": page_blocks,
                "images": [],
                "coverage": coverage,
            }
        )

    stats = {
        "page_count": len(pages),
        "block_count": block_total,
        "images": 0,
        "avg_coverage": (sum(coverages) / len(coverages)) if coverages else 0.0,
    }
    return pages, stats


_EXTRACTORS: list[tuple[str, Callable[[bytes, str], tuple[list[dict[str, Any]], dict[str, Any]]]]] = [
    ("pymupdf", _pymupdf_extract),
    ("pdfplumber", _pdfplumber_extract),
    ("pdfminer", _pdfminer_extract),
]


def _text_extract(payload: bytes, doc_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Final fallback that treats the payload as UTF-8/latin-1 encoded text."""

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        text = payload.decode("latin-1", errors="ignore")

    segments = re.split(r"\f|\n{3,}", text)
    if not segments:
        segments = [text]

    pages: list[dict[str, Any]] = []
    coverages: list[float] = []
    block_total = 0
    image_total = 0
    for page_index, segment in enumerate(segments, start=1):
        images: list[dict[str, Any]] = []
        for match in _IMAGE_PATTERN.finditer(segment):
            images.append(
                {
                    "id": f"{doc_id}:p{page_index}:img{len(images) + 1}",
                    "description": match.group("name").strip(),
                }
            )
        image_total += len(images)
        stripped = _IMAGE_PATTERN.sub("", segment).strip()
        if not stripped:
            pages.append(
                {
                    "page_number": page_index,
                    "text": "",
                    "blocks": [],
                    "images": images,
                    "coverage": 0.0,
                }
            )
            coverages.append(0.0)
            continue
        blocks: list[dict[str, Any]] = []
        lines = [line.strip() for line in re.split(r"\n{2,}", stripped) if line.strip()]
        for block_index, line in enumerate(lines, start=1):
            blocks.append(
                {
                    "id": f"{doc_id}:p{page_index}:b{block_index}",
                    "page": page_index,
                    "text": line,
                    "bbox": [0.0, 0.0, 1.0, 1.0],
                    "font": {
                        "family": "SourceSans",
                        "size": 12.0,
                        "weight": "normal",
                        "style": "normal",
                    },
                    "confidence": 0.5,
                }
            )
        block_total += len(blocks)
        coverage = 1.0 if blocks else 0.0
        coverages.append(coverage)
        pages.append(
            {
                "page_number": page_index,
                "text": "\n".join(lines),
                "blocks": blocks,
                "images": images,
                "coverage": coverage,
            }
        )

    stats = {
        "page_count": len(pages),
        "block_count": block_total,
        "images": image_total,
        "avg_coverage": (sum(coverages) / len(coverages)) if coverages else 0.0,
    }
    return pages, stats


def normalize_pdf(
    doc_id: str,
    *,
    file_id: str | None = None,
    file_name: str | None = None,
    source_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Extract text/layout/style into a normalized JSON."""

    payload = source_bytes or b""
    audit_records = [
        stage_record(
            stage="normalize.load",
            status="ok",
            bytes=len(payload),
            doc_id=doc_id,
        )
    ]

    pages: list[dict[str, Any]] = []
    stats: dict[str, Any] = {
        "page_count": 0,
        "block_count": 0,
        "images": 0,
        "avg_coverage": 0.0,
        "source_bytes": len(payload),
    }
    extractor_used: str | None = None
    last_error: Exception | None = None

    for name, extractor in _EXTRACTORS:
        try:
            pages, extracted_stats = extractor(payload, doc_id)
            extractor_used = name
            stats.update(extracted_stats)
            break
        except Exception as exc:  # noqa: BLE001 - controlled fallback
            last_error = exc
            logger.warning(
                "upload.normalize_pdf.extractor_failed",
                extra={"doc_id": doc_id, "extractor": name, "error": str(exc)},
            )
            continue

    if not pages:
        try:
            pages, extracted_stats = _text_extract(payload, doc_id)
            extractor_used = "text"
            stats.update(extracted_stats)
        except Exception as exc:  # noqa: BLE001 - defensive fallback
            last_error = exc if last_error is None else last_error
            pages = []

    if not pages:
        if last_error is not None:
            raise last_error
        raise ValueError("failed to extract pages from PDF")

    audit_records.append(
        stage_record(
            stage="normalize.extract",
            status="ok",
            extractor=extractor_used,
            pages=len(pages),
            blocks=stats.get("block_count", 0),
            avg_coverage=stats.get("avg_coverage", 0.0),
        )
    )

    audit_records.append(
        stage_record(
            stage="normalize.summary",
            status="ok",
            pages=len(pages),
            blocks=stats.get("block_count", 0),
            avg_coverage=stats.get("avg_coverage", 0.0),
        )
    )

    normalized: dict[str, Any] = {
        "doc_id": doc_id,
        "source": {"file_id": file_id, "file_name": file_name},
        "pages": pages,
        "stats": stats,
        "audit": audit_records,
    }

    logger.info(
        "upload.normalize_pdf",
        extra={
            "doc_id": doc_id,
            "pages": stats.get("page_count", 0),
            "blocks": stats.get("block_count", 0),
            "avg_coverage": stats.get("avg_coverage", 0.0),
            "extractor": extractor_used,
        },
    )
    return normalized
