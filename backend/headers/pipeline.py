from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from backend.efhg.entropy import (
    DEFAULT_SEED_QUANTILE,
    DEFAULT_STOP_QUANTILE,
    compute_entropy_features,
    score_starts,
    score_stops,
    select_quantile_ids,
)
from backend.efhg.fluid import DEFAULT_PARAMS as FLUID_DEFAULTS, Span, build_edges, grow_span_from_seed
from backend.efhg.graph_gate import DEFAULT_PARAMS as GRAPH_DEFAULTS, GraphContext, score_graph, snap_and_trim
from backend.efhg.hep import DEFAULT_PARAMS as HEP_DEFAULTS, score_span_hep
from backend.headers.header_llm import (
    VerifiedHeader,
    VerifiedHeaders,
    aggressive_sequence_repair,
    build_header_prompt,
    call_llm,
    parse_fenced_outline,
    verify_headers,
)
from backend.uf_chunker import HEADER_PATTERN, UFChunk, uf_chunk


@dataclass
class HeaderIndex:
    doc_id: str
    headers: List[Dict[str, Any]]
    uf_chunks: List[UFChunk]
    spans: List[Dict[str, Any]]
    output_dir: Path


def _ensure_output_dir(doc_id: str, output_dir: str | Path | None) -> Path:
    if output_dir is None:
        base = Path("uploads") / doc_id
    else:
        base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)
    return base


def _span_to_audit(span: Span, start_scores: Dict[str, float], stop_scores: Dict[str, float], hep_scores: Dict[str, Any], graph_score: float, graph_penalties: Dict[str, float], decision: str) -> Dict[str, Any]:
    return {
        "header_label": _extract_label(span.text),
        "page": span.page,
        "span": span.span,
        "chunk_ids": span.chunk_ids,
        "scores": {
            "entropy": {
                "S_start": start_scores.get(span.chunk_ids[0], 0.0),
                "S_stop": stop_scores.get(span.chunk_ids[-1], 0.0),
            },
            "fluid": {
                "Flow_total": span.flow_total,
                "edges_used": max(0, len(span.chunk_ids) - 1),
            },
            "hep": hep_scores,
            "graph": {
                "S_graph": graph_score,
                "penalties": graph_penalties,
            },
            "final": hep_scores["S_HEP"] + span.flow_total - sum(graph_penalties.values()),
        },
        "decision": decision,
        "text_preview": span.text[:120],
    }


def _extract_label(text: str) -> str | None:
    for line in text.splitlines():
        match = HEADER_PATTERN.search(line.strip())
        if match:
            return match.group(0)
    return None


def _serialize_verified(headers: VerifiedHeaders) -> List[Dict[str, Any]]:
    return [
        {
            "label": header.label,
            "text": header.text,
            "page": header.page,
            "span": header.span,
            "verification": header.verification,
            "source": header.source,
            "confidence": header.confidence,
        }
        for header in headers.headers
    ]


def _persist_jsonl(path: Path, records: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_headers(doc_id: str, decomp: Dict[str, Any]) -> HeaderIndex:
    pages = decomp.get("pages", [])
    pages_norm = [page.get("text", "") for page in pages]
    pages_raw = [page.get("raw_text", page.get("text", "")) for page in pages]
    tokens_per_page = [page.get("tokens", []) for page in pages]
    output_dir = _ensure_output_dir(doc_id, decomp.get("output_dir"))

    uf_chunks = uf_chunk(decomp)
    compute_entropy_features(uf_chunks)
    start_scores = score_starts(uf_chunks)
    stop_scores = score_stops(uf_chunks)
    edges = build_edges(uf_chunks)

    messages = build_header_prompt(pages_norm)
    llm_raw = ""
    verified_headers: VerifiedHeaders
    llm_error: str | None = None
    try:
        llm_raw = call_llm(messages)
        parsed = parse_fenced_outline(llm_raw)
        verified_headers = verify_headers(parsed, pages_norm, pages_raw)
    except Exception as exc:  # pylint: disable=broad-except
        llm_error = str(exc)
        verified_headers = VerifiedHeaders()

    repaired_headers = aggressive_sequence_repair(verified_headers, pages_norm, tokens_per_page)
    header_ctx = GraphContext(
        headers=[
            {
                "label": header.label,
                "text": header.text,
                "page": header.page,
                "span": header.span,
            }
            for header in repaired_headers.headers
        ],
        references=decomp.get("references", []),
        tables=decomp.get("tables", []),
    )

    seed_candidates = select_quantile_ids(start_scores, DEFAULT_SEED_QUANTILE)
    chunk_lookup = {chunk.id: chunk for chunk in uf_chunks}
    seed_ids = [cid for cid in seed_candidates if chunk_lookup.get(cid) and chunk_lookup[cid].header_anchor]
    if not seed_ids:
        seed_ids = [chunk.id for chunk in uf_chunks if chunk.header_anchor]
    spans_audit: List[Dict[str, Any]] = []
    accepted_spans: List[Span] = []

    for seed_id in seed_ids:
        span = grow_span_from_seed(seed_id, uf_chunks, edges, stop_scores)
        span = snap_and_trim(span, header_ctx, chunk_lookup)
        hep_detail = score_span_hep(span, chunk_lookup)
        graph_score, graph_penalties = score_graph(span, header_ctx, chunk_lookup)
        final_score = hep_detail["S_HEP"] + span.flow_total - sum(graph_penalties.values())
        decision = "rejected"
        if hep_detail["S_HEP"] >= HEP_DEFAULTS["theta_hep"] and final_score >= GRAPH_DEFAULTS["theta_final"]:
            decision = "accepted"
            accepted_spans.append(span)
        spans_audit.append(_span_to_audit(span, start_scores, stop_scores, hep_detail, graph_score, graph_penalties, decision))

    final_headers_map: Dict[str, VerifiedHeader] = {header.label: header for header in repaired_headers.headers}
    for span in accepted_spans:
        label = _extract_label(span.text)
        if not label:
            continue
        canonical_text = span.text.split(label, 1)[-1].strip()
        final_headers_map[label] = VerifiedHeader(
            label=label,
            text=canonical_text,
            page=span.page,
            span=span.span,
            verification={"status": "efhg"},
            source="efhg",
            confidence=0.9,
        )

    if llm_error and not final_headers_map:
        for span in accepted_spans:
            label = _extract_label(span.text)
            if not label:
                continue
            final_headers_map[label] = VerifiedHeader(
                label=label,
                text=span.text.split(label, 1)[-1].strip(),
                page=span.page,
                span=span.span,
                verification={"status": "efhg_fallback"},
                source="efhg_fallback",
                confidence=0.75,
            )

    final_headers = sorted(final_headers_map.values(), key=lambda h: (h.page, h.span[0], h.label))

    headers_payload = [
        {
            "level": header.label.rstrip(".)"),
            "label": header.label,
            "text": header.text,
            "page": header.page,
            "span": header.span,
            "source": header.source,
            "confidence": header.confidence,
        }
        for header in final_headers
    ]

    uf_records = [
        {
            "id": chunk.id,
            "page": chunk.page,
            "span": chunk.span_char,
            "text": chunk.text,
            "style": chunk.style,
            "lex": chunk.lex,
            "entropy": chunk.entropy,
            "header_anchor": chunk.header_anchor,
        }
        for chunk in uf_chunks
    ]

    efhg_records = spans_audit

    audit_payload = {
        "config": {
            "uf_max_tokens": 90,
            "uf_overlap": 12,
            "entropy": {"weights": {"w1": 0.7, "w2": 0.2, "w3": 0.1, "w4": 0.6, "w5": 0.25, "w6": 0.15}, "seed_quantile": DEFAULT_SEED_QUANTILE, "stop_quantile": DEFAULT_STOP_QUANTILE},
            "fluid": FLUID_DEFAULTS,
            "hep": HEP_DEFAULTS,
            "graph": GRAPH_DEFAULTS,
        },
        "uf_chunks": [
            {
                "id": chunk.id,
                "page": chunk.page,
                "span": chunk.span_char,
                "text_preview": chunk.preview(),
                "style": chunk.style,
                "lex": chunk.lex,
                "entropy": chunk.entropy,
                "header_anchor": chunk.header_anchor,
            }
            for chunk in uf_chunks
        ],
        "llm_headers": {
            "raw_fenced_json": llm_raw,
            "verified": _serialize_verified(verified_headers),
            "error": llm_error,
        },
        "sequence_repair": repaired_headers.repair_log,
        "efhg_header_spans": spans_audit,
        "final_headers": headers_payload,
    }

    _persist_jsonl(output_dir / "uf_chunks.jsonl", uf_records)
    _persist_jsonl(output_dir / "efhg_spans.jsonl", efhg_records)
    with (output_dir / "headers.json").open("w", encoding="utf-8") as handle:
        json.dump(headers_payload, handle, ensure_ascii=False, indent=2)
    with (output_dir / "candidate_audit.json").open("w", encoding="utf-8") as handle:
        json.dump(audit_payload, handle, ensure_ascii=False, indent=2)

    return HeaderIndex(
        doc_id=doc_id,
        headers=headers_payload,
        uf_chunks=uf_chunks,
        spans=efhg_records,
        output_dir=output_dir,
    )


__all__ = ["run_headers", "HeaderIndex"]
