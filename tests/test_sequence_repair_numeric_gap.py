from __future__ import annotations

import json
from pathlib import Path

from tests.header_pipeline_utils import run_header_pipeline


def test_sequence_repair_inserts_missing_numeric(tmp_path: Path) -> None:
    text = (
        "8) Scope overview\n"
        "Background narrative.\n"
        "9) Safety provisions and monitoring\n"
        "Detailed considerations.\n"
        "10) Closing remarks\n"
    )

    def fake_llm(_messages: object) -> str:
        payload = {
            "headers": [
                {"label": "8)", "text": "Scope overview", "page": 1},
                {"label": "10)", "text": "Closing remarks", "page": 1},
            ]
        }
        return "```json\n" + json.dumps(payload) + "\n```"

    output_dir = tmp_path / "numeric"
    output_dir.mkdir()
    result = run_header_pipeline("doc-numeric", text, output_dir, call_llm=fake_llm)

    headers = {header["label"]: header for header in result.headers}
    assert "9)" in headers
    assert headers["9)"]["source"] == "repair"

    promoted = json.loads((output_dir / "headers_promoted.json").read_text())
    numeric_repairs = [
        entry
        for entry in promoted
        if entry.get("promotion_reason") == "sequence_repair" and entry.get("pattern") == "numeric_section"
    ]
    assert numeric_repairs, "Sequence repair promotion should be logged for numeric header"

    audit = json.loads((output_dir / "candidate_audit.json").read_text())
    repair_entries = [entry for entry in audit["sequence_repair"] if entry["series"] == "NUMERIC"]
    assert repair_entries, "Expected numeric repair entry"
    found = any(item["label"] == "9)" for entry in repair_entries for item in entry["result"])
    assert found, "Numeric repair should record inserted header"
