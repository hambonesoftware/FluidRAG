from __future__ import annotations

import json
from pathlib import Path

from backend.headers import pipeline as pipeline_module
from backend.headers.gap_probe import _canonical_label
from tests.header_pipeline_utils import run_header_pipeline


def test_gap_probe_logging_emits_records(tmp_path: Path) -> None:
    text = (
        "A3. Piping overview\n"
        "Details about piping.\n"
        "A4. Controls & Electrical\n"
        "Panel SCCR (kA): ____ A5. Utilities & Consumption data inline.\n"
        "A6. Performance metrics listed here.\n"
        "A7. Safety observations\n"
        "A8. Testing and validation\n"
        "Appendix B Additional resources\n"
    )

    original_scan = pipeline_module.scan_candidates
    original_repair = pipeline_module.aggressive_sequence_repair

    def filtered_scan(chunks):
        results = original_scan(chunks)
        filtered = [
            candidate
            for candidate in results
            if _canonical_label(candidate.label) not in {"A5", "A6"}
        ]
        return filtered

    def passthrough_repair(verified, pages_norm, tokens):
        return verified

    pipeline_module.scan_candidates = filtered_scan  # type: ignore[assignment]
    pipeline_module.aggressive_sequence_repair = passthrough_repair  # type: ignore[assignment]

    def fake_llm(_messages: object) -> str:
        payload = {
            "headers": [
                {"label": "A4.", "text": "Controls & Electrical", "page": 1},
                {"label": "A7.", "text": "Safety observations", "page": 1},
            ]
        }
        return "```json\n" + json.dumps(payload) + "\n```"

    output_dir = tmp_path / "gap"
    output_dir.mkdir()
    try:
        run_header_pipeline("doc-gap", text, output_dir, call_llm=fake_llm)
    finally:
        pipeline_module.scan_candidates = original_scan  # type: ignore[assignment]
        pipeline_module.aggressive_sequence_repair = original_repair  # type: ignore[assignment]

    jsonl_path = output_dir / "gap_probes.jsonl"
    assert jsonl_path.exists(), "Expected gap probe log"
    lines = [line for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1, "Expected a single gap entry"
    entry = json.loads(lines[0])
    assert entry["event"] == "gap_probe"
    assert entry["page"] == 1
    assert entry["expected_next"] == ["A5", "A6"]
    stage = entry["candidate_stage"]
    assert stage["emitted_A5"] is False
    assert stage["emitted_A6"] is False
    reasons = stage["reasons"]
    assert reasons and reasons[0]["token"] == "A5"
    assert "no_line_start_flag" in reasons[0]["why_not"] or "not_in_page_text" in reasons[0]["why_not"]
    assert reasons[1]["token"] == "A6"
    assert any("gap_guard" in reason for reason in reasons[1]["why_not"])

    tsv_path = output_dir / "gap_probes.tsv"
    assert tsv_path.exists(), "Expected gap probe TSV"
    rows = [line.split("\t") for line in tsv_path.read_text(encoding="utf-8").strip().splitlines()]
    assert len(rows) == 2
    header = rows[0]
    data = rows[1]
    assert header[0:4] == ["page", "prev", "next_expected", "found_on_page"]
    assert data[0] == "1"
    assert "A5|A6" in data[2]
    assert data[-1] != ""

