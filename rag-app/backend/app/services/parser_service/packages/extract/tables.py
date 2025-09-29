"""Table extraction heuristics."""

from __future__ import annotations

import re
from typing import Any

_SEPARATOR = re.compile(r"[\t|]")


def extract_tables(normalized: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract tables with cell grid."""
    tables: list[dict[str, Any]] = []
    for page in normalized.get("pages", []):
        page_number = page.get("page_number", 0)
        rows: list[list[str]] = []
        for line in page.get("text", "").splitlines():
            if "|" not in line and "\t" not in line:
                continue
            cells = [cell.strip() for cell in _SEPARATOR.split(line) if cell.strip()]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(
                {
                    "id": f"{normalized['doc_id']}:p{page_number}:tbl{len(tables) + 1}",
                    "page": page_number,
                    "rows": rows,
                }
            )
    return tables
