"""Table extraction heuristics backed by pdfplumber."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .....util.logging import get_logger

logger = get_logger(__name__)


def extract_tables(normalized: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract tables with structured cell grids."""

    source_path = normalized.get("source", {}).get("path")
    if not source_path or not Path(source_path).exists():
        return []

    tables: list[dict[str, Any]] = []
    try:
        import pdfplumber

        with pdfplumber.open(source_path) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                extracted = page.extract_tables() or []
                for table_index, table in enumerate(extracted, start=1):
                    rows = [[cell.strip() if cell else "" for cell in row] for row in table]
                    tables.append(
                        {
                            "id": f"{normalized['doc_id']}:p{index}:tbl{table_index}",
                            "page": index,
                            "rows": rows,
                            "bbox": list(page.bbox),
                        }
                    )
    except Exception as exc:  # pragma: no cover - optional dependency errors
        logger.warning(
            "parser.extract_tables.failed",
            extra={"path": source_path, "error": str(exc)},
        )
    return tables
