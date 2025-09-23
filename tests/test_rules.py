import pytest

from chunking import rules


def test_heading_breaks_no_cross_section():
    chunk = {
        "id": "test",
        "text": "1) Intro\nSomething\n2) Scope\nElse",
        "section_number": "1",
    }
    result = rules.apply_rules([chunk], {"hard_heading_breaks": True, "page_footer_scrub": False, "list_stitching": False, "appendix_microchunking": False, "soft_split_on_view": False})
    assert len(result) == 2
    assert {c["section_number"] for c in result} == {"1", "2"}


def test_page_footer_scrub_removes_artifacts():
    chunk = {"id": "p", "text": "4) Heading\n12\nBody\ni"}
    result = rules.apply_rules([chunk], {"hard_heading_breaks": False, "page_footer_scrub": True, "list_stitching": False, "appendix_microchunking": False, "soft_split_on_view": False})
    assert "12" not in result[0]["text"]
    assert "\ni" not in result[0]["text"]


def test_list_stitching_merges_wrapped_bullets():
    chunk = {"id": "l", "text": "- Provide\nsupport structure\n- Keep.\nNext"}
    result = rules.apply_rules([chunk], {"hard_heading_breaks": False, "page_footer_scrub": False, "list_stitching": True, "appendix_microchunking": False, "soft_split_on_view": False})
    assert "Provide support structure" in result[0]["text"]
    assert "Keep." in result[0]["text"]


def test_appendix_b_split_rows():
    chunk = {
        "id": "tbl",
        "text": "Appendix B Pricing\nLine  Item  Description  Qty  Unit\n1  Conveyor  Base  2  ea\n2  Guard  Base  1  ea",
    }
    result = rules.apply_rules([chunk], {"hard_heading_breaks": False, "page_footer_scrub": False, "list_stitching": False, "appendix_microchunking": True, "soft_split_on_view": False})
    assert len(result) == 2
    assert all(r.get("chunk_type") == "table_row" for r in result)


def test_soft_split_respects_allowlist():
    chunk = {
        "id": "soft",
        "text": "6) Controls\nBody\n7) Software\nBody",
        "section_number": "6",
    }
    parts = rules.soft_split_on_headings(chunk, {"7"})
    assert len(parts) == 1
    assert parts[0]["section_number"] == "7"
