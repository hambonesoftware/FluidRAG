from __future__ import annotations

import json
from pathlib import Path

from backend.efhg.hep import DEFAULT_PARAMS as HEP_DEFAULTS

from tests.header_pipeline_utils import run_header_pipeline


def test_header_split_across_uf(tmp_path: Path) -> None:
    base_line = (
        "A5. Utilities & Consumption shall include 34 MW feeders and 12 kV distribution "
        "with shall statements [1]."
    )
    filler = " More metrics shall align with 24 MW feeders and 7 kV loops." * 6
    text = base_line + filler

    output_dir = tmp_path / "split"
    output_dir.mkdir()
    result = run_header_pipeline("doc-split", text, output_dir)

    assert result.uf_chunks, "UF chunking should produce chunks"
    assert len(result.uf_chunks) > 1, "Header should span multiple UF chunks"

    audit = json.loads((output_dir / "candidate_audit.json").read_text())
    accepted = [
        entry
        for entry in audit["efhg_header_spans"]
        if entry.get("header_label") == "A5." and entry["decision"] in {"accepted", "promoted"}
    ]
    assert accepted, "Expected promoted EFHG span for split header"
    span_entry = accepted[0]
    assert span_entry["scores"]["fluid"]["Flow_total"] > 0
    assert span_entry["scores"]["hep"]["S_HEP"] >= HEP_DEFAULTS["theta_hep"]
    assert "cross_bleed" in span_entry["scores"]["graph"]["penalties"]
