import json

from backend.headers.llm_header_pass import coerce_llm_candidates, parse_llm_json


def test_coerce_llm_candidates_from_json():
    raw = json.dumps(
        {
            "headers": [
                {
                    "title": "Introduction",
                    "page": 1,
                    "confidence": 0.92,
                    "level": "1",
                    "section_id": "1",
                    "summary": "preface",
                }
            ]
        }
    )
    items = parse_llm_json(raw)
    candidates = coerce_llm_candidates(items)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.title == "Introduction"
    assert candidate.page == 1
    assert candidate.level == 1
    assert candidate.section_id == "1"
    assert candidate.judging.llm_confidence == 0.92
    # Arbitrary keys from the JSON payload should be preserved for auditing.
    assert candidate.judging.llm_raw_fields == {"summary": "preface"}


def test_parse_llm_json_with_wrapper_and_span():
    raw = json.dumps(
        {
            "results": [
                {
                    "title": "Scope",
                    "page": "2",
                    "confidence": 0.81,
                    "level": "2",
                    "id": "1.1",
                    "span_char": {"start": 5, "end": 17},
                    "notes": "subsection",
                }
            ]
        }
    )
    items = parse_llm_json(raw)
    candidates = coerce_llm_candidates(items)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.section_id == "1.1"
    assert candidate.level == 2
    assert candidate.page == 2
    assert candidate.span_char == (5, 17)
    assert candidate.judging.llm_confidence == 0.81
    assert candidate.judging.llm_raw_fields == {"notes": "subsection"}
