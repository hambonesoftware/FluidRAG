from __future__ import annotations

import json
from dataclasses import asdict
from typing import Dict, List, Optional

from backend.models.headers import FinalHeader, HeaderCandidate


def _normalise_span(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return [value[0], value[1]]
    return list(value) if isinstance(value, (set,)) else value


def candidate_to_dict(candidate: HeaderCandidate) -> Dict[str, object]:
    payload = asdict(candidate)
    payload["span_char"] = _normalise_span(payload.get("span_char"))
    judging = payload.get("judging")
    if isinstance(judging, dict):
        judging["span_char"] = _normalise_span(judging.get("span_char"))
    return payload


def final_to_dict(final: FinalHeader) -> Dict[str, object]:
    payload = asdict(final)
    payload["span_char"] = _normalise_span(payload.get("span_char"))
    return payload


def write_preprocess_audit(
    *,
    doc_meta: Optional[Dict[str, object]],
    llm_raw_response: str,
    llm_parse_error: Optional[str],
    llm_candidates: List[HeaderCandidate],
    heuristic_candidates: List[HeaderCandidate],
    final_headers: List[FinalHeader],
    out_path: str = "Epf_Co.preprocess.json",
) -> None:
    payload = {
        "doc_meta": doc_meta or {},
        "header_pass": {
            "llm": {
                "prompt_used": "Please list all header sections of this document and provide the results in a json format",
                "raw_response": llm_raw_response,
                "parse_error": llm_parse_error,
                "candidates": [candidate_to_dict(c) for c in llm_candidates],
            },
            "heuristic": {
                "candidates": [candidate_to_dict(c) for c in heuristic_candidates],
            },
            "final": {
                "headers": [final_to_dict(f) for f in final_headers],
            },
        },
    }
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


__all__ = ["candidate_to_dict", "final_to_dict", "write_preprocess_audit"]
