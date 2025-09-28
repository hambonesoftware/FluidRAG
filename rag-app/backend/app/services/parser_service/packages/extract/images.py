"""Image placeholder extraction."""
from __future__ import annotations

from typing import List

from backend.app.contracts.parsing import ImageBlock


def extract_images(pages: List[str]) -> List[ImageBlock]:
    images: List[ImageBlock] = []
    for page_num, page in enumerate(pages, start=1):
        for line in page.splitlines():
            if line.lower().startswith("figure"):
                images.append(ImageBlock(page=page_num, description=line.strip(), path=None))
    return images
