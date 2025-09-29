"""Image extraction helpers."""

from __future__ import annotations

from typing import Any


def extract_images(normalized: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract images & captions."""
    images: list[dict[str, Any]] = []
    for page in normalized.get("pages", []):
        for image in page.get("images", []):
            images.append(
                {
                    "id": image.get("id"),
                    "page": page.get("page_number", 0),
                    "description": image.get("description", ""),
                }
            )
    return images
