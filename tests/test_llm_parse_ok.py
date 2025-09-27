from backend.headers.llm_header_pass import coerce_llm_candidates, parse_llm_json


def test_coerce_llm_candidates_from_json():
    raw = '{"headers": [{"title": "Introduction", "page": 1, "confidence": 0.92, "level": "1", "section_id": "1"}]}'
    items = parse_llm_json(raw)
    candidates = coerce_llm_candidates(items)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.title == "Introduction"
    assert candidate.page == 1
    assert candidate.level == 1
    assert candidate.judging.llm_confidence == 0.92
