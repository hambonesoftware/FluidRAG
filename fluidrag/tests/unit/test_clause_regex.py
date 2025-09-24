from __future__ import annotations

from fluidrag.src.graph.build import CLAUSE_REGEX, STANDARD_REGEX


def test_detects_named_standards():
    text = "Comply with NFPA 79 and IEC 60204-1:2018 requirements."
    matches = [m.group() for m in STANDARD_REGEX.finditer(text)]
    assert "NFPA 79" in matches
    assert any("IEC 60204-1" in match for match in matches)


def test_detects_clause_pattern():
    clause_text = "Refer to section 5.3.3 for details."
    matches = CLAUSE_REGEX.findall(clause_text)
    assert "5.3.3" in matches
