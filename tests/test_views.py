from chunking.views import build_views


def test_views_controls_must_hit_sections():
    chunks = [
        {"id": "c1", "text": "7) Controls\nPLC details", "section_number": "7", "meta": {"hep_entropy_z": 0.2}},
        {"id": "c2", "text": "10) Safety\nSafety notes", "section_number": "10", "meta": {"hep_entropy_z": 0.3}},
        {"id": "c3", "text": "8) Other\n", "section_number": "8", "meta": {"hep_entropy_z": 0.0}},
    ]
    views = build_views(
        chunks,
        {
            "controls": {
                "must_sections": ["7", "10"],
                "section_allowlist": ["7", "8", "9", "10", "11"],
                "keywords": ["PLC", "safety"],
                "hep_z_min": -1,
                "length_budget_tokens": 300,
            }
        },
        {"soft_split_on_view": True, "hard_heading_breaks": True, "page_footer_scrub": True, "list_stitching": True, "appendix_microchunking": True},
    )
    sections = {chunk["section_number"] for chunk in views["controls"]}
    assert {"7", "10"}.issubset(sections)
