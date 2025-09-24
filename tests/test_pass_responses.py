"""Tests for parsing and exporting pass responses."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from backend.pipeline.passes.responses import encode_rows_to_csv, parse_pass_response


def test_parse_pass_response_recovers_spilled_pass_column() -> None:
    csv_text = (
        "Document,(Sub)Section #,(Sub)Section Name,Specification,Pass\n"
        "Doc,1,Intro,Seal joints, RH 30-70%,Mechanical\n"
        "Doc,2,Intro,Use UL-listed hardware,,\n"
    )
    rows, csv_block, json_block = parse_pass_response(csv_text, "Mechanical")

    assert csv_block is not None
    assert json_block is None
    assert len(rows) == 2
    assert rows[0]["Specification"] == "Seal joints, RH 30-70%"
    assert rows[0]["Pass"] == "Mechanical"
    # Second row should inherit the last valid pass value.
    assert rows[1]["Pass"] == "Mechanical"


def test_encode_rows_quotes_comma_fields() -> None:
    rows = [
        {
            "Document": "Doc",
            "(Sub)Section #": "1",
            "(Sub)Section Name": "Intro",
            "Specification": "Seal joints, RH 30-70%",
            "Pass": "Mechanical",
        }
    ]

    csv_output = encode_rows_to_csv(rows)
    assert '"Seal joints, RH 30-70%"' in csv_output
