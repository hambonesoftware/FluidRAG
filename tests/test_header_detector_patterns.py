import pytest

from backend.parse.header_detector import is_header_line, normalize_heading_text
from backend.parse.header_page_mode import _extract_section_number


@pytest.mark.parametrize(
    "line",
    [
        "Appendix B — Pricing Breakdown (Template)",
        "Appendix Pricing Overview",
        "B Pricing Breakdown (Template)",
        "C - Spare Parts Listing",
    ],
)
def test_appendix_headers_detected(line: str) -> None:
    ok, _meta = is_header_line(line, style={"font_sigma_rank": 1.6, "bold": True})
    assert ok, f"Expected appendix-style header to be detected: {line!r}"


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Appendix B — Pricing Breakdown (Template)", "Appendix B"),
        ("Appendix Pricing Overview", "Appendix Pricing"),
        ("B Pricing Breakdown (Template)", "B"),
        ("C - Spare Parts Listing", "C"),
    ],
)
def test_extract_section_number_for_appendix_forms(line: str, expected: str) -> None:
    normalized = normalize_heading_text(line)
    section_number = _extract_section_number(normalized)
    assert (
        section_number == expected
    ), f"Expected {expected!r} but got {section_number!r} for line {line!r}"
