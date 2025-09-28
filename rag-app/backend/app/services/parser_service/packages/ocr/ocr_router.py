"""Decide whether OCR is required."""
from __future__ import annotations

from typing import List

from backend.app.services.upload_service.packages.normalize.ocr import try_ocr_if_needed
from backend.app.services.upload_service.packages.normalize.pdf_reader import normalize_pdf


def maybe_ocr(content: bytes) -> List[str]:
    pages = normalize_pdf(content)
    if any(page.strip() for page in pages):
        return pages
    return try_ocr_if_needed(content)
