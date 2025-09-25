"""Tests for appendix header detection and pass post-processing helpers."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chunking.instrumentation import detect_heading_spans
from backend.pipeline.passes.chunking import build_pass_groups
from backend.pipeline.passes.runner import _assign_sections_to_rows, _dedupe_rows


def test_appendix_subheaders_detected() -> None:
    text = (
        "Appendix A — Integration Overview\n"
        "A4. Controls & Electrical Interfaces\n"
        "A5. Utilities & Consumption\n"
        "A6. Safety Systems\n"
    )
    spans = detect_heading_spans(text)
    labels = {label for label, _, _ in spans}
    assert {"A4", "A5", "A6"} <= labels


def test_assign_sections_populates_fields() -> None:
    lookup = [
        {
            "section_number": "A5",
            "section_name": "Utilities & Consumption",
            "text": "A5. Utilities & Consumption\nProvide chilled water connection.",
            "normalized_text": "a5. utilities & consumption provide chilled water connection.",
        }
    ]
    rows = [
        {
            "Document": "Spec.pdf",
            "(Sub)Section #": "",
            "(Sub)Section Name": "",
            "Specification": "Provide chilled water connection.",
            "Pass": "Mechanical",
        }
    ]
    coverage = _assign_sections_to_rows(rows, lookup)
    assert coverage == pytest.approx(1.0)
    assert rows[0]["(Sub)Section #"] == "A5"
    assert rows[0]["(Sub)Section Name"].startswith("Utilities")


def test_build_pass_groups_filters_domain() -> None:
    chunks = [
        {
            "text": "PLC programming shall use GuardLogix safety functions.",
            "section_number": "A4",
            "section_name": "Controls",
            "document": "Spec",
            "meta": {},
        },
        {
            "text": "Provide warranty milestones and training schedule.",
            "section_number": "PM1",
            "section_name": "Project Management",
            "document": "Spec",
            "meta": {},
        },
    ]
    base_groups, per_pass = build_pass_groups(chunks)
    assert len(base_groups) >= 1
    controls_groups = per_pass.get("Controls", [])
    controls_texts = [
        chunk["text"]
        for group in controls_groups
        for chunk in group.get("chunks", [])
    ]
    assert controls_texts == [
        "PLC programming shall use GuardLogix safety functions."
    ]


def test_dedupe_rows_merges_pass_sources() -> None:
    rows = [
        {
            "Document": "Spec.pdf",
            "(Sub)Section #": "A4",
            "(Sub)Section Name": "Controls",
            "Specification": "Provide PLC programming per NFPA 79.",
            "Pass": "Controls",
        },
        {
            "Document": "Spec.pdf",
            "(Sub)Section #": "A4",
            "(Sub)Section Name": "Controls",
            "Specification": "Provide PLC programming per NFPA 79.",
            "Pass": "Mechanical",
        },
    ]
    deduped, overlap = _dedupe_rows(rows)
    assert len(deduped) == 1
    assert deduped[0]["Pass"] == "Controls; Mechanical"
    assert overlap == pytest.approx(0.5)
