from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from fluidrag.backend.core.pipeline import run_pipeline


def _doc_all_passes() -> dict:
    return {
        "doc_id": "DOC-ALL-PASSES",
        "lines": [
            {
                "page": 1,
                "line_idx": 0,
                "text": "1) Performance Requirements",
                "font_size": 13.5,
                "bold": True,
                "bbox": [0, 0, 220, 24],
            },
            {
                "page": 1,
                "line_idx": 1,
                "text": "The system shall maintain spindle speed at 1800 rpm ± 50 rpm.",
                "font_size": 11.0,
                "bold": False,
                "bbox": [0, 24, 520, 48],
            },
            {
                "page": 1,
                "line_idx": 2,
                "text": "See §4 for safety response criteria.",
                "font_size": 11.0,
                "bold": False,
                "bbox": [0, 48, 480, 72],
            },
            {
                "page": 2,
                "line_idx": 0,
                "text": "2) Electrical Requirements",
                "font_size": 13.5,
                "bold": True,
                "bbox": [0, 0, 240, 24],
            },
            {
                "page": 2,
                "line_idx": 1,
                "text": "SCCR shall be ≥ 65 kA at 480 VAC.",
                "font_size": 11.0,
                "bold": False,
                "bbox": [0, 24, 520, 48],
            },
            {
                "page": 2,
                "line_idx": 2,
                "text": "Provide grounding conductors sized for 40 A feeders.",
                "font_size": 11.0,
                "bold": False,
                "bbox": [0, 48, 520, 72],
            },
            {
                "page": 3,
                "line_idx": 0,
                "text": "3) Software Configuration",
                "font_size": 13.5,
                "bold": True,
                "bbox": [0, 0, 260, 24],
            },
            {
                "page": 3,
                "line_idx": 1,
                "text": "The PLC shall run firmware version 4.2 and log events at ≥ 1 Hz.",
                "font_size": 11.0,
                "bold": False,
                "bbox": [0, 24, 540, 48],
            },
            {
                "page": 3,
                "line_idx": 2,
                "text": "HMI shall store audit trails for 30 days.",
                "font_size": 11.0,
                "bold": False,
                "bbox": [0, 48, 520, 72],
            },
            {
                "page": 4,
                "line_idx": 0,
                "text": "4) Controls and Safety",
                "font_size": 13.5,
                "bold": True,
                "bbox": [0, 0, 240, 24],
            },
            {
                "page": 4,
                "line_idx": 1,
                "text": "Emergency stops shall react in ≤ 0.20 s.",
                "font_size": 11.0,
                "bold": False,
                "bbox": [0, 24, 500, 48],
            },
            {
                "page": 4,
                "line_idx": 2,
                "text": "Light curtains must meet SIL 2 requirements.",
                "font_size": 11.0,
                "bold": False,
                "bbox": [0, 48, 520, 72],
            },
            {
                "page": 5,
                "line_idx": 0,
                "text": "5) Project Management",
                "font_size": 13.5,
                "bold": True,
                "bbox": [0, 0, 240, 24],
            },
            {
                "page": 5,
                "line_idx": 1,
                "text": "Provide FAT, SAT, and training documentation within 30 days.",
                "font_size": 11.0,
                "bold": False,
                "bbox": [0, 24, 540, 48],
            },
            {
                "page": 5,
                "line_idx": 2,
                "text": "Warranty coverage shall be ≥ 12 months from acceptance.",
                "font_size": 11.0,
                "bold": False,
                "bbox": [0, 48, 520, 72],
            },
        ],
    }


def _appendix_gap_document() -> dict:
    return {
        "doc_id": "DOC-APPENDIX-GAP",
        "lines": [
            {
                "page": 7,
                "line_idx": 0,
                "text": "A3. Spare Hardware",
                "font_size": 13.5,
                "bold": True,
                "bbox": [0, 0, 200, 24],
            },
            {
                "page": 7,
                "line_idx": 1,
                "text": "The kit shall include 10 spare bolts and 10 spare nuts.",
                "font_size": 11.0,
                "bold": False,
                "bbox": [0, 24, 500, 48],
            },
            {
                "page": 7,
                "line_idx": 2,
                "text": "A4. Spare Motors",
                "font_size": 13.5,
                "bold": True,
                "bbox": [0, 48, 200, 72],
            },
            {
                "page": 7,
                "line_idx": 3,
                "text": "Provide two backup motors rated at 5 kW each.",
                "font_size": 11.0,
                "bold": False,
                "bbox": [0, 72, 520, 96],
            },
            {
                "page": 7,
                "line_idx": 4,
                "text": "A7. Drawings",
                "font_size": 13.5,
                "bold": True,
                "bbox": [0, 96, 180, 120],
            },
            {
                "page": 7,
                "line_idx": 5,
                "text": "All schematics shall be delivered as native CAD files.",
                "font_size": 11.0,
                "bold": False,
                "bbox": [0, 120, 520, 144],
            },
            {
                "page": 7,
                "line_idx": 6,
                "text": "A8. Bill of Materials",
                "font_size": 13.5,
                "bold": True,
                "bbox": [0, 144, 220, 168],
            },
            {
                "page": 7,
                "line_idx": 7,
                "text": "Submit the BOM within 14 days of FAT completion.",
                "font_size": 11.0,
                "bold": False,
                "bbox": [0, 168, 520, 192],
            },
        ],
    }


def test_fluidrag_v2_pipeline_end_to_end(tmp_path: Path):
    document = _doc_all_passes()
    queries = {
        "mechanical": "spindle speed requirement",
        "electrical": "SCCR 65 kA at 480 VAC",
        "software": "PLC firmware logging",
        "controls": "safety response SIL",
        "pm": "FAT SAT training warranty",
    }

    artifact = run_pipeline(document, queries)

    sections = artifact["sections"]["sections"]
    assert len(sections) == 5

    # Graph sidecar must include NEXT ordering and at least one REFERS_TO link
    edges = artifact["section_graph"]["edges"]
    assert any(edge["type"] == "REFERS_TO" for edge in edges)
    assert sum(1 for edge in edges if edge["type"] == "NEXT") == len(sections) - 1

    # Micro-chunks should carry doc-invariant scoring and provenance
    assert artifact["chunks"], "Micro-chunks were not generated"
    for chunk in artifact["chunks"]:
        assert 0.0 <= chunk["E"] <= 1.0
        assert 0.0 <= chunk["F"] <= 1.0
        assert 0.0 <= chunk["H"] <= 1.0
        assert chunk["provenance"]["bboxes"]

    # Each pass (0-5) should return deterministic retrieval with extractions
    for pass_name in ("mechanical", "electrical", "software", "controls", "pm"):
        payload = artifact["retrieval"][pass_name]
        assert payload["deterministic"] is True
        assert payload["final_chunks"], f"No chunks selected for {pass_name}"
        assert len(payload["final_chunks"]) <= artifact["config"]["retrieval"]["K_final"]
        assert payload["extractions"], f"No extractions produced for {pass_name}"
        assert payload["validations"]["parse_rate"] >= 0.95

    # CI gates must all evaluate to true for the full artifact
    ci_summary = artifact["ci"]
    assert all(ci_summary.values())

    artifact_path = tmp_path / "pipeline_artifact.json"
    artifact_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    cmd = [sys.executable, "scripts/run_ci_checks.py", str(artifact_path)]
    completed = subprocess.run(cmd, check=True, capture_output=True, text=True)
    assert "All checks passed" in completed.stdout


def test_appendix_gap_logging():
    document = _appendix_gap_document()
    queries = {"mechanical": "spare hardware"}

    artifact = run_pipeline(document, queries)

    gaps = artifact["section_gaps"]
    assert gaps, "Expected appendix gap detection entries"
    assert any("appendix_sequence_gap" == gap.get("gap_reason") for gap in gaps)
    assert artifact["ci"]["appendix_gaps_logged"] is True
