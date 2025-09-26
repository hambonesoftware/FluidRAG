from __future__ import annotations

import json
from pathlib import Path

from tests.header_pipeline_utils import run_header_pipeline


def test_sequence_repair_appx_gap(tmp_path: Path) -> None:
    text = (
        "A4. Prior Results\n"
        "Shall deliver baseline study.\n"
        "A5. Utilities & Consumption\n"
        "Utilities shall include 34 MW of load.\n"
        "A6. Performance\n"
        "Performance shall improve by 5%.\n"
        "A7. Closing Actions\n"
        "Complete project integration."
    )

    def fake_llm(_messages: object) -> str:
        payload = {
            "headers": [
                {"label": "A4.", "text": "Prior Results", "page": 1},
                {"label": "A7.", "text": "Closing Actions", "page": 1},
            ]
        }
        return "```json\n" + json.dumps(payload) + "\n```"

    output_dir = tmp_path / "seq"
    output_dir.mkdir()
    result = run_header_pipeline("doc-seq", text, output_dir, call_llm=fake_llm)

    final_headers = {header["label"]: header for header in result.headers}
    assert "A5." in final_headers and final_headers["A5."]["source"] == "repair"
    assert "A6." in final_headers and final_headers["A6."]["source"] == "repair"

    audit = json.loads((output_dir / "candidate_audit.json").read_text())
    gap_entry = next((entry for entry in audit["sequence_repair"] if entry["gap"].startswith("A5")), None)
    assert gap_entry is not None
    assert gap_entry["series"] == "APPX"
    assert gap_entry["before"]["text"].startswith("Prior")
    assert gap_entry["after"]["text"].startswith("Closing")
    assert gap_entry["result"], "Expected repair candidates logged"
    for candidate in gap_entry["result"]:
        assert candidate["confidence"] >= 0.55
        assert candidate["method"] in {"regex", "header_resegment", "soft_unwrap+regex", "ocr_window"}
