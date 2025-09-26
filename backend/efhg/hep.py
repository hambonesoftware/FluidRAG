from __future__ import annotations

from typing import Dict

from backend.uf_chunker import UFChunk
from backend.efhg.fluid import Span

DEFAULT_PARAMS = {
    "a": 1.0,
    "b": 0.9,
    "c": 0.6,
    "d": 0.8,
    "e": 0.7,
    "theta_hep": 2.0,
}


def _span_has_feature(span: Span, chunks: Dict[str, UFChunk], predicate) -> bool:
    return any(predicate(chunks[cid]) for cid in span.chunk_ids)


def score_span_hep(span: Span, chunks: Dict[str, UFChunk], params: Dict[str, float] | None = None) -> Dict[str, object]:
    params = params or DEFAULT_PARAMS
    modal = _span_has_feature(span, chunks, lambda c: c.lex.get("has_modal"))
    constraints = _span_has_feature(span, chunks, lambda c: bool(c.lex.get("numbers")) and bool(c.lex.get("units")))
    citations = _span_has_feature(span, chunks, lambda c: c.lex.get("citation_hints"))
    completeness = len(span.chunk_ids) >= 1 and len(span.text.split()) > 3
    ambiguity = len({chunks[cid].style.get("font_size") for cid in span.chunk_ids}) > 2

    score = (
        params["a"] * (1.0 if modal else 0.0)
        + params["b"] * (1.0 if constraints else 0.0)
        + params["c"] * (1.0 if citations else 0.0)
        + params["d"] * (1.0 if completeness else 0.0)
        - params["e"] * (1.0 if ambiguity else 0.0)
    )

    details = {
        "S_HEP": score,
        "modal": modal,
        "constraints": constraints,
        "citations": citations,
        "completeness": completeness,
        "ambiguity": ambiguity,
    }
    return details


__all__ = ["score_span_hep", "DEFAULT_PARAMS"]
