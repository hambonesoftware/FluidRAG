"""Helpers for interpreting LLM pass responses."""
from __future__ import annotations

import csv
import io
from typing import Dict, List, Optional, Tuple

from backend.utils.strings import s

from .constants import ALL_PASSES, CSV_COLUMNS


VALID_PASS_LOOKUP = {pass_name.lower(): pass_name for pass_name in [*ALL_PASSES, "Header"]}


def _normalize_pass(value: str) -> Optional[str]:
    """Return the canonical pass name if the supplied value is valid."""

    if not value:
        return None
    return VALID_PASS_LOOKUP.get(value.lower())


def parse_pass_response(text: str, pass_name: str) -> Tuple[List[Dict[str, str]], Optional[str], Optional[str]]:
    """Extract CSV and JSON fragments from an LLM response."""

    if not text:
        return [], None, None
    csv_block: Optional[str] = None
    json_block: Optional[str] = None
    lower = text.lower()
    if "===csv===" in lower:
        split_csv = text.split("===CSV===", 1)[1]
    else:
        split_csv = text
    if "===JSON===" in split_csv:
        csv_part, json_part = split_csv.split("===JSON===", 1)
        csv_block = csv_part.strip()
        json_block = json_part.strip()
    else:
        csv_block = split_csv.strip()

    rows: List[Dict[str, str]] = []
    last_valid_pass = _normalize_pass(pass_name) or pass_name
    if csv_block:
        reader = csv.DictReader(io.StringIO(csv_block))
        for row in reader:
            if not any(row.values()):
                continue
            normalized = {col: s(row.get(col)) for col in CSV_COLUMNS}
            spec = normalized.get("Specification", "")
            raw_pass = normalized.get("Pass", "")
            canonical_pass = _normalize_pass(raw_pass)
            if canonical_pass:
                normalized["Pass"] = canonical_pass
                last_valid_pass = canonical_pass
            else:
                if raw_pass:
                    normalized["Specification"] = ", ".join(
                        fragment for fragment in (spec, raw_pass) if fragment
                    )
                normalized["Pass"] = last_valid_pass or pass_name
            rows.append(normalized)
    return rows, csv_block, json_block


def encode_rows_to_csv(rows: List[Dict[str, str]]) -> str:
    """Serialise rows for download."""

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=CSV_COLUMNS,
        extrasaction="ignore",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({col: row.get(col, "") for col in CSV_COLUMNS})
    return buffer.getvalue()
