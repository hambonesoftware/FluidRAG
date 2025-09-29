"""Hyperlink extraction."""

from __future__ import annotations

import re
from typing import Any

_URL_PATTERN = re.compile(r"https?://[\w\-._~:/?#\[\]@!$&'()*+,;=%]+")


def extract_links(normalized: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract hyperlinks/crossrefs."""
    links: list[dict[str, Any]] = []
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
