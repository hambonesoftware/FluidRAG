import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest import assign_micro_to_sections, build_sections, microchunk_text


def _make_parts(text: str, section_id: str, section_title: str, chunk_id: str, doc_id: str = "doc-1"):
    return {
        "doc_id": doc_id,
        "section_id": section_id,
        "section_title": section_title,
        "chunk_id": chunk_id,
        "header_anchor": f"anchor-{section_id}",
        "text": text,
    }


def test_boundary_alignment_respects_bullets():
    text = (
        "The system shall provide operator dashboards with clear alarms. "
        "Each station shall report availability and downtime.\n"
        "• Maintain 95% availability for 60 s.\n"
        "• Provide diagnostics for all stations.\n"
        "Compliance data shall be logged hourly to support audits."
    )
    parts = [_make_parts(text, "11.2", "HMI Functions", "chunk-001")]
    chunks = microchunk_text(parts, size=30, overlap=8)
    assert len(chunks) >= 2
    for chunk in chunks[:-1]:
        tail = chunk["text"].strip()
        assert tail.endswith(".") or tail.endswith("stations."), tail
        assert chunk["style"] is not None
        assert isinstance(chunk["lex"], dict)
        assert len(chunk["emb"]) == 8


def test_overlap_contains_numeric_phrase():
    text = (
        "The motor shall sustain 18 cpm for ≥ 60 s under full load without overheating. "
        "This performance shall be verified monthly and recorded in the maintenance log."
    )
    parts = [_make_parts(text, "12.1", "Performance", "chunk-002")]
    chunks = microchunk_text(parts, size=25, overlap=10)
    phrase = "18 cpm for ≥ 60 s"
    coverage = [phrase in chunk["text"] for chunk in chunks]
    assert any(coverage)
    assert sum(coverage) >= 1
    if len(chunks) > 1:
        assert sum(coverage) >= 1  # Overlap should at least keep the phrase intact once


def test_section_assignment_selects_correct_section():
    part_a = _make_parts("Section 1 intro. Requirements shall apply.", "1.0", "Introduction", "chunk-100")
    part_b = _make_parts("Section 2 content with tables and figures.", "2.0", "Scope", "chunk-200")
    parts = [part_a, part_b]
    micros = microchunk_text(parts, size=15, overlap=5)
    doc = {"doc_id": "doc-1", "chunks": parts}
    sections = build_sections(doc)
    mapping = assign_micro_to_sections(micros, sections)
    assert "1.0" in mapping
    assert "2.0" in mapping
    assert any(mid for mid in mapping["1.0"] if micros[0]["micro_id"] == mid)
    assert micros[0]["domain_hint"] in {None, "performance", "quality", "safety"}


def test_microchunk_determinism():
    parts = [
        _make_parts("Consistency check sentence one. Sentence two for hashing.", "3.1", "Consistency", "chunk-300")
    ]
    first = microchunk_text(parts, size=20, overlap=5)
    second = microchunk_text(parts, size=20, overlap=5)
    assert [chunk["micro_id"] for chunk in first] == [chunk["micro_id"] for chunk in second]
