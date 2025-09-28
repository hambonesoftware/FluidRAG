"""Extract hyperlinks."""
from __future__ import annotations

import re
from typing import List

from backend.app.contracts.parsing import LinkBlock


_LINK_RE = re.compile(r"(https?://\S+)")


def extract_links(pages: List[str]) -> List[LinkBlock]:
    links: List[LinkBlock] = []
    for page_num, page in enumerate(pages, start=1):
        for match in _LINK_RE.finditer(page):
            links.append(LinkBlock(page=page_num, text=match.group(0), target=match.group(1)))
    return links
