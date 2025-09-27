from __future__ import annotations

from typing import Dict, List, Optional

from backend.audit.preprocess_writer import write_preprocess_audit
from backend.headers.heuristic_adapter import run_heuristic_header_pass
from backend.headers.llm_header_pass import run_llm_header_pass
from backend.headers.merge_headers import merge_candidates
def run_header_pipeline(
    full_normalized_text: str,
    heuristic_records: List[Dict[str, object]],
    doc_meta: Optional[Dict[str, object]] = None,
    *,
    audit_path: Optional[str] = None,
) -> Dict[str, object]:
    """Run heuristic + LLM header passes and write the preprocess audit."""

    doc_meta_copy = dict(doc_meta or {})
    heuristic_candidates = run_heuristic_header_pass(heuristic_records, doc_meta=doc_meta_copy)
    llm_result = run_llm_header_pass(full_normalized_text)
    llm_candidates = llm_result.get("candidates", [])
    final_headers = merge_candidates(llm_candidates, heuristic_candidates)

    write_preprocess_audit(
        doc_meta=doc_meta_copy,
        llm_raw_response=llm_result.get("raw_response", ""),
        llm_parse_error=llm_result.get("parse_error"),
        llm_candidates=llm_candidates,
        heuristic_candidates=heuristic_candidates,
        final_headers=final_headers,
        out_path=audit_path or "Epf_Co.preprocess.json",
    )

    return {
        "heuristic_candidates": heuristic_candidates,
        "llm_result": llm_result,
        "final_headers": final_headers,
    }


__all__ = ["run_header_pipeline"]
