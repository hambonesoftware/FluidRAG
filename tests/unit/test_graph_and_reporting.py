from fluidrag.backend.core.extraction.provenance import to_overlay
from fluidrag.backend.core.graph.loader import build_graph
from fluidrag.backend.core.graph.query import neighbors
from fluidrag.backend.core.reporting.html_report import render


def test_graph_has_chunk_edges():
    sections = [
        {"sec_id": "S0000", "page": 1, "line_idx": 1, "kind": "numeric", "title": "Performance"},
        {"sec_id": "S0001", "page": 2, "line_idx": 5, "kind": "numeric", "title": "Safety"},
    ]
    chunks = [
        {"chunk_id": "C1", "section_id": "S0000"},
        {"chunk_id": "C2", "section_id": "S0001"},
    ]
    graph = build_graph("doc-1", sections, chunks)
    assert neighbors(graph, "doc-1", "HAS_SECTION") == ["S0000", "S0001"]
    assert neighbors(graph, "S0000", "HAS_CHUNK") == ["C1"]
    assert neighbors(graph, "S0000", "NEXT") == ["S0001"]


def test_html_report_and_provenance_overlay():
    record = {"section_id": "S1", "text": "The system shall.", "page": 3, "provenance": {"bboxes": [[0, 0, 10, 10]]}}
    overlay = to_overlay(record)
    assert overlay["bboxes"] == [[0, 0, 10, 10]]
    html = render("doc-123", [record], [overlay])
    assert "doc-123" in html
    assert "Overlays" in html
