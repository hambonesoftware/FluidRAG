"""PDF normalization utilities."""
from __future__ import annotations

from typing import List


def normalize_pdf(content: bytes) -> List[str]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1", errors="ignore")
    pages = [page.strip() for page in text.split("\f") if page.strip()]
    if not pages:
        pages = [text.strip()]
    return pages
