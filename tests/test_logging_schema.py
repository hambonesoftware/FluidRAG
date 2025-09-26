from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from tests.header_pipeline_utils import run_header_pipeline


def test_logging_schema(tmp_path: Path) -> None:
    text = "A1. Introduction\nThis shall outline 10 MW baselines."
    output_dir = tmp_path / "schema"
    output_dir.mkdir()
    result = run_header_pipeline("doc-schema", text, output_dir)

    assert result.headers, "Final headers should be present"

    audit_path = output_dir / "candidate_audit.json"
    audit = json.loads(audit_path.read_text())
    schema_path = Path("schemas/candidate_audit.schema.json")
    schema = json.loads(schema_path.read_text())

    Draft202012Validator(schema).validate(audit)

    for entry in audit["final_headers"]:
        assert "page" in entry and "span" in entry and "source" in entry
        assert entry["span"] == entry.get("span_char")
