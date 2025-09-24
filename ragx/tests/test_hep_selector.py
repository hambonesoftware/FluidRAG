import yaml

from ragx.core.context import RAGContext
from ragx.core.hep import select_hep_passages


def test_hep_prefers_units_and_standards():
    profiles = yaml.safe_load(open("ragx/config/profiles.yaml", "r", encoding="utf-8"))
    profile = profiles["passes"]["Mechanical"]
    context = RAGContext(doc_id="tiny", ppass="Mechanical", intent="RETRIEVE", domain="Mechanical", version="test")
    sections = [
        {
            "section_id": "S1",
            "text": "All frames shall use ASTM A36 steel with thickness 10 mm. This is descriptive text only.",
            "anchors": ["1 — Mechanical"],
            "pages": [1],
            "provenance": ["S1"],
            "signals": {"delta_entropy": [0.2, 0.4]},
        },
    ]
    passages = select_hep_passages(sections, profile, context)
    assert passages, "should produce passages"
    best = passages[0]
    assert "10 mm" in best["text"]
    assert "resolution" in best and best["resolution"] == "hep"
