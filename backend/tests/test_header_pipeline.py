from __future__ import annotations

import json
import re
from pathlib import Path

from backend.efhg.hep import DEFAULT_PARAMS as HEP_DEFAULTS
from backend.headers.pipeline import run_headers


def _tokens_for_text(text: str, font_size: float = 12.0, indent: float = 0.0):
    tokens = []
    for match in re.finditer(r"\S+\s*", text):
        tokens.append(
            {
                "text": match.group(0),
                "start": match.start(),
                "end": match.end(),
                "font_size": font_size,
                "bold": match.group(0).strip().endswith("."),
                "indent": indent,
            }
        )
    return tokens


def _run_pipeline(doc_id: str, text: str, tmp_path: Path, call_llm=None):
    page = {
        "text": text,
        "tokens": _tokens_for_text(text),
    }
    decomp = {"pages": [page], "output_dir": tmp_path}
    original_call = None
    if call_llm:
        from backend.headers import pipeline as pipeline_module

        original_call = pipeline_module.call_llm
        pipeline_module.call_llm = call_llm  # type: ignore[assignment]
    try:
        return run_headers(doc_id, decomp)
    finally:
        if call_llm:
            from backend.headers import pipeline as pipeline_module

            pipeline_module.call_llm = original_call  # type: ignore[assignment]


def test_sequence_repair_appx_gap(tmp_path):
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

    def fake_llm(_messages):
        payload = {
            "headers": [
                {"label": "A4.", "text": "Prior Results", "page": 1},
                {"label": "A7.", "text": "Closing Actions", "page": 1},
            ]
        }
        return "```json\n" + json.dumps(payload) + "\n```"

    output_dir = tmp_path / "seq"
    output_dir.mkdir()
    result = _run_pipeline("doc-seq", text, output_dir, call_llm=fake_llm)
    final_headers = {header["label"]: header for header in result.headers}
    assert "A5." in final_headers and final_headers["A5."]["source"] == "repair"
    assert "A6." in final_headers and final_headers["A6."]["source"] == "repair"

    audit = json.loads((output_dir / "candidate_audit.json").read_text())
    assert any(entry["gap"].startswith("A5") for entry in audit["sequence_repair"])


def test_header_split_across_uf(tmp_path):
    base_line = "A5. Utilities & Consumption shall include 34 MW feeders and 12 kV distribution with shall statements [1]."
    filler = " More metrics shall align with 24 MW feeders and 7 kV loops." * 3
    text = base_line + filler

    output_dir = tmp_path / "split"
    output_dir.mkdir()
    result = _run_pipeline("doc-split", text, output_dir)
    audit = json.loads((output_dir / "candidate_audit.json").read_text())
    accepted = [
        entry
        for entry in audit["efhg_header_spans"]
        if entry["decision"] == "accepted" and entry.get("header_label") == "A5."
    ]
    assert accepted, "Expected accepted EFHG span for split header"
    span_entry = accepted[0]
    assert span_entry["scores"]["fluid"]["Flow_total"] > 0
    assert span_entry["scores"]["hep"]["S_HEP"] >= HEP_DEFAULTS["theta_hep"]


def test_logging_schema(tmp_path):
    text = "A1. Introduction\nThis shall outline 10 MW baselines."
    output_dir = tmp_path / "schema"
    output_dir.mkdir()
    result = _run_pipeline("doc-schema", text, output_dir)
    audit_path = output_dir / "candidate_audit.json"
    audit = json.loads(audit_path.read_text())

    required_top = [
        "config",
        "uf_chunks",
        "llm_headers",
        "sequence_repair",
        "efhg_header_spans",
        "final_headers",
    ]
    for key in required_top:
        assert key in audit, f"Missing section {key}"

    config = audit["config"]
    assert config["uf_max_tokens"] == 90
    assert config["uf_overlap"] == 12
    for section in ("entropy", "fluid", "hep", "graph"):
        assert section in config

    for chunk in audit["uf_chunks"]:
        assert set(["id", "page", "span", "style", "lex", "entropy", "header_anchor"]).issubset(chunk.keys())

    llm_headers = audit["llm_headers"]
    assert "raw_fenced_json" in llm_headers
    assert "verified" in llm_headers

    for entry in audit["final_headers"]:
        for field in ("page", "span", "source"):
            assert field in entry

    candidate = next((entry for entry in audit["final_headers"] if entry["label"].startswith("A1")), None)
    assert candidate is not None
