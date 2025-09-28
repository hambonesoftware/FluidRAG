"""Extract text blocks from normalized pages."""
from __future__ import annotations

from typing import List

from backend.app.contracts.parsing import TextBlock

from ..detect.language import detect_language


def extract_text_blocks(doc_id: str, pages: List[str]) -> List[TextBlock]:
    blocks: List[TextBlock] = []
    order = 0
    for page_num, page in enumerate(pages, start=1):
        language = detect_language(page)
        for paragraph in filter(None, (p.strip() for p in page.split("\n\n"))):
            blocks.append(TextBlock(page=page_num, content=paragraph, language=language, order=order))
            order += 1
    return blocks
