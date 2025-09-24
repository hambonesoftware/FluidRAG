import yaml

from ragx.core.context import RAGContext
from ragx.core.fluid import merge_fluid


def test_fluid_merge_requires_similarity_and_tags():
    profiles = yaml.safe_load(open("ragx/config/profiles.yaml", "r", encoding="utf-8"))
    profile = profiles["passes"]["Mechanical"]
    context = RAGContext(doc_id="tiny", ppass="Mechanical", intent="RETRIEVE", domain="Mechanical", version="test")
    sections = [
        {
            "section_id": "S1",
            "section_name": "dimensions and material",
            "start_idx": 0,
            "page_start": 1,
            "page_end": 1,
            "anchors": ["1 — Dimensions"],
            "tags": ["dimensions", "material"],
        },
        {
            "section_id": "S2",
            "section_name": "material and finish",
            "start_idx": 1,
            "page_start": 1,
            "page_end": 1,
            "anchors": ["2 — Finish"],
            "tags": ["material", "finish"],
        },
        {
            "section_id": "S3",
            "section_name": "unrelated info",
            "start_idx": 2,
            "page_start": 2,
            "page_end": 2,
            "anchors": ["3 — Other"],
            "tags": ["other"],
        },
    ]
    embeddings = [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]]
    merged = merge_fluid(sections, profile, context, embeddings=embeddings)
    assert len(merged) == 2
    first = merged[0]
    assert set(first["provenance"]) == {"S1", "S2"}
    assert "resolution" in first and first["resolution"] == "fluid"
