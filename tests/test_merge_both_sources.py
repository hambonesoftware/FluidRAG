from backend.headers.merge_headers import merge_candidates
from backend.models.headers import HeaderCandidate, Judging


def _candidate(
    source: str,
    title: str,
    section_id: str | None,
    confidence: float,
    page: int,
    *,
    reasons: list[str] | None = None,
) -> HeaderCandidate:
    judging = Judging(
        heuristic_confidence=confidence if source == "heuristic" else None,
        llm_confidence=confidence if source == "llm" else None,
        page=page,
        reasons=list(reasons or []),
    )
    return HeaderCandidate(
        source=source,
        section_id=section_id,
        title=title,
        level=1,
        page=page,
        span_char=None,
        judging=judging,
    )


def test_merge_candidates_prefers_both_sources():
    heur = _candidate("heuristic", "Introduction", "1", 0.7, 1)
    llm = _candidate("llm", "Introduction", "1", 0.8, 1)

    merged = merge_candidates([llm], [heur])
    assert len(merged) == 1
    final = merged[0]
    assert final.section_id == "1"
    assert final.sources == ["heuristic", "llm"]
    assert final.confidence > 0.7
    assert "supported_by_both_sources" in final.reasons


def test_merge_candidates_collects_reason_metadata():
    heur = _candidate(
        "heuristic",
        "Introduction",
        "1",
        0.65,
        1,
        reasons=["numeric_pattern", "bold_text"],
    )
    llm = _candidate("llm", "Introduction", "1", 0.8, 1, reasons=["high_confidence"])

    merged = merge_candidates([llm], [heur])
    final = merged[0]

    assert "source:heuristic" in final.reasons
    assert "source:llm" in final.reasons
    assert "heuristic:numeric_pattern" in final.reasons
    assert "heuristic:bold_text" in final.reasons
    assert "llm:high_confidence" in final.reasons
