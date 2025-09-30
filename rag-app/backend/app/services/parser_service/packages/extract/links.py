"""Hyperlink extraction."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .....util.logging import get_logger

logger = get_logger(__name__)

_URL_PATTERN = re.compile(r"https?://[\w\-._~:/?#\[\]@!$&'()*+,;=%]+")


def extract_links(normalized: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract hyperlinks/crossrefs."""
    links: list[dict[str, Any]] = []

    source_path = normalized.get("source", {}).get("path")
    if source_path and Path(source_path).exists():
        try:
            import fitz  # type: ignore

            with fitz.open(source_path) as document:
                for index, page in enumerate(document, start=1):
                    for item in page.get_links():
                        uri = item.get("uri")
                        if not uri:
                            continue
                        links.append(
                            {
                                "page": index,
                                "url": uri,
                                "kind": item.get("kind"),
                                "bbox": item.get("from"),
                            }
                        )
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "parser.extract_links.failed",
                extra={"path": source_path, "error": str(exc)},
            )

    for page in normalized.get("pages", []):
        page_number = page.get("page_number", 0)
        for match in _URL_PATTERN.finditer(page.get("text", "")):
            links.append(
                {
                    "page": page_number,
                    "url": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                }
            )
    return links
