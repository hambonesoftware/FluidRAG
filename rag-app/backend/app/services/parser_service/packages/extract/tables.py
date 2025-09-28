"""Extract simple tables."""
from __future__ import annotations

from typing import List

from backend.app.contracts.parsing import TableBlock


def extract_tables(pages: List[str]) -> List[TableBlock]:
    tables: List[TableBlock] = []
    for page_num, page in enumerate(pages, start=1):
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        grid = [line for line in lines if "|" in line]
        if grid:
            rows = [row.split("|") for row in grid]
            tables.append(TableBlock(page=page_num, rows=[list(map(str.strip, row)) for row in rows], caption=None))
    return tables
