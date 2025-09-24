import yaml

from ragx.core.context import RAGContext
from ragx.core.segmentation import detect_headers


def test_detect_headers_respects_min_gap():
    profiles = yaml.safe_load(open("ragx/config/profiles.yaml", "r", encoding="utf-8"))
    profile = profiles["passes"]["Mechanical"]
    context = RAGContext(doc_id="tiny", ppass="Mechanical", intent="HEADER", domain="Mechanical", version="test")
    chunks = [
        {"text": "1. Scope", "meta": {"page": 1, "is_heading": True, "section_id": "S1", "number": "1."}},
        {"text": "Body text one.", "meta": {"page": 1}},
        {"text": "2. Details", "meta": {"page": 2, "is_heading": True, "section_id": "S2", "number": "2."}},
        {"text": "Another paragraph.", "meta": {"page": 2}},
    ]
    sections = detect_headers(chunks, None, None, profile, context)
    assert [sec["start_idx"] for sec in sections] == [0, 2]
    assert all(sec["break_score"] > 0 for sec in sections)
