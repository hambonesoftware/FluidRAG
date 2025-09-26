from __future__ import annotations

import json
from pathlib import Path

from tests.header_pipeline_utils import run_header_pipeline


def test_appendix_and_numeric_patterns_promote(tmp_path: Path) -> None:
    text = (
        "General overview Appendix B — Instrumentation scope details\n"
        "Support systems include multiple feeds A5. Utilities Provided for operators\n"
        "Follow-on narrative referencing A.1 Startup Procedure for commissioning\n"
    )

    output_dir = tmp_path / "patterns"
    output_dir.mkdir()

    result = run_header_pipeline("doc-patterns", text, output_dir)

    labels = {header["label"] for header in result.headers}
    assert "Appendix B" in labels
    assert "A5." in labels
    assert "A.1" in labels

    promoted = json.loads((output_dir / "headers_promoted.json").read_text())
    reasons = {entry.get("promotion_reason") for entry in promoted}
    assert "pattern" in reasons
    appendix_entries = [
        entry
        for entry in promoted
        if entry.get("pattern") == "appendix_top" and entry.get("promotion_reason") == "pattern"
    ]
    assert appendix_entries, "Expected Appendix promotion to be logged"
    numeric_entries = [
        entry
        for entry in promoted
        if entry.get("pattern") == "appendix_sub_AN" and entry.get("promotion_reason") == "pattern"
    ]
    assert numeric_entries, "Expected subsection promotion to be logged"

    suppressed = json.loads((output_dir / "headers_suppressed.json").read_text())
    assert all(entry.get("reason", {}).get("reason") == "span_collision" for entry in suppressed)
