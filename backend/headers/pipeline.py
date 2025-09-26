from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from backend.efhg.entropy import (
    DEFAULT_WEIGHTS,
    DEFAULT_SEED_QUANTILE,
    DEFAULT_STOP_QUANTILE,
    compute_entropy_features,
    score_starts,
    score_stops,
    select_quantile_ids,
)
from backend.efhg.fluid import (
    DEFAULT_PARAMS as FLUID_DEFAULTS,
    Span,
    build_edges,
    grow_span_from_seed,
)
from backend.efhg.graph_gate import DEFAULT_PARAMS as GRAPH_DEFAULTS, GraphContext, score_graph, snap_and_trim
from backend.efhg.hep import DEFAULT_PARAMS as HEP_DEFAULTS, score_span_hep
from backend.headers.config import HEADER_GATE_MODE, STRICT_CONFLICT_ONLY
from backend.headers.header_llm import (
    VerifiedHeader,
    VerifiedHeaders,
    aggressive_sequence_repair,
    build_header_prompt,
    call_llm,
    parse_fenced_outline,
    verify_headers,
)
from backend.headers.header_scan import HeaderCandidate, promote_candidates, scan_candidates
from backend.uf_chunker import HEADER_PATTERN, UFChunk, uf_chunk


@dataclass
class HeaderIndex:
    doc_id: str
    headers: List[Dict[str, Any]]
    uf_chunks: List[UFChunk]
    spans: List[Dict[str, Any]]
    header_shards: List[Dict[str, Any]]
    output_dir: Path


_PATTERN_PRIORITY = {
    "appendix_top": 4,
    "numeric_section": 3,
    "appendix_sub_AN": 2,
    "appendix_sub_AlN": 2,
}


@dataclass
class SpanRecord:
    seed_id: str
    span: Span
    candidate: HeaderCandidate | None
    hep: Dict[str, Any]
    graph_score: float
    graph_penalties: Dict[str, float]
    start_score: float
    stop_score: float
    final_score: float
    decision: str
    accepted: bool
    promotion_reason: str | None = None
    conflicts_resolved: List[Dict[str, Any]] = field(default_factory=list)
    suppression_reason: str | None = None


def _pattern_rank(record: SpanRecord) -> int:
    if record.candidate:
        return _PATTERN_PRIORITY.get(record.candidate.pattern, 1)
    return 1


def _priority_key(record: SpanRecord, llm_labels: Set[str]) -> Tuple[float, ...]:
    candidate = record.candidate
    font_size = 0.0
    bold = 0
    indent = 0.0
    label = ""
    if candidate:
        style = candidate.style or {}
        font_size = float(style.get("font_size") or 0.0)
        bold = 1 if style.get("bold") else 0
        indent = float(style.get("indent") or 0.0)
        label = candidate.label
    if not label:
        label = _extract_label(record.span.text) or ""
    llm_vote = 1 if label and label in llm_labels else 0
    return (
        float(_pattern_rank(record)),
        font_size,
        bold,
        -indent,
        llm_vote,
        record.span.flow_total,
        -float(record.span.span[0]),
    )


def _span_overlap(left: SpanRecord, right: SpanRecord) -> int:
    a_start, a_end = left.span.span
    b_start, b_end = right.span.span
    return max(0, min(a_end, b_end) - max(a_start, b_start))


def _resolve_conflicts(
    records: List[SpanRecord],
    llm_labels: Set[str],
) -> Tuple[List[SpanRecord], List[SpanRecord]]:
    accepted = [record for record in records if record.accepted]
    for record in accepted:
        record.conflicts_resolved.clear()
        record.suppression_reason = None

    sorted_records = sorted(
        accepted,
        key=lambda rec: _priority_key(rec, llm_labels),
        reverse=True,
    )

    kept: List[SpanRecord] = []
    suppressed: List[SpanRecord] = []
    for record in sorted_records:
        has_conflict = False
        for winner in kept:
            overlap = _span_overlap(winner, record)
            if overlap <= 0:
                continue
            has_conflict = True
            record.accepted = False
            record.decision = "conflict_suppressed"
            loser_label = record.candidate.label if record.candidate else _extract_label(record.span.text)
            winner_label = winner.candidate.label if winner.candidate else _extract_label(winner.span.text)
            record.suppression_reason = {
                "reason": "span_collision",
                "winner": winner_label,
                "overlap": overlap,
            }
            winner.conflicts_resolved.append(
                {
                    "loser": loser_label,
                    "overlap": overlap,
                    "seed_id": record.seed_id,
                }
            )
            suppressed.append(record)
            break
        if not has_conflict:
            kept.append(record)

    for winner in kept:
        if winner.conflicts_resolved and not winner.promotion_reason:
            winner.promotion_reason = "conflict_keep"

    return kept, suppressed

def _ensure_output_dir(doc_id: str, output_dir: str | Path | None) -> Path:
    if output_dir is None:
        base = Path("uploads") / doc_id
    else:
        base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)
    return base


def _span_to_audit(
    span: Span,
    start_scores: Dict[str, float],
    stop_scores: Dict[str, float],
    hep_scores: Dict[str, Any],
    graph_score: float,
    graph_penalties: Dict[str, float],
    decision: str,
) -> Dict[str, Any]:
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


def _build_header_shards(
    final_headers: List[VerifiedHeader],
    accepted_spans: List[Span],
    chunk_lookup: Dict[str, UFChunk],
) -> List[Dict[str, Any]]:
    spans_by_label: Dict[str, Span] = {}
    for span in accepted_spans:
        label = _extract_label(span.text)
        if label and label not in spans_by_label:
            spans_by_label[label] = span

    shards: List[Dict[str, Any]] = []
    for header in final_headers:
        label = header.label
        span = spans_by_label.get(label)
        if span:
            chunk_ids = list(span.chunk_ids)
            text_preview = span.text.strip()
        else:
            candidates = [
                chunk
                for chunk in chunk_lookup.values()
                if chunk.page == header.page and label in chunk.text
            ]
            if candidates:
                chunk_ids = [candidates[0].id]
                text_preview = candidates[0].text.strip()
            else:
                chunk_ids = []
                text_preview = f"{label} {header.text}".strip()
        shards.append(
            {
                "label": label,
                "page": header.page,
                "span": header.span,
                "span_char": header.span,
                "chunk_ids": chunk_ids,
                "text": text_preview,
                "source": header.source,
                "confidence": header.confidence,
            }
        )
    return shards


def run_headers(doc_id: str, decomp: Dict[str, Any]) -> HeaderIndex:
    pages = decomp.get("pages", [])
    pages_norm = [page.get("text", "") for page in pages]
    pages_raw = [page.get("raw_text", page.get("text", "")) for page in pages]
    tokens_per_page = [page.get("tokens", []) for page in pages]
    output_dir = _ensure_output_dir(doc_id, decomp.get("output_dir"))

    uf_chunks = uf_chunk(decomp)
    candidates = scan_candidates(uf_chunks)
    promote_candidates(candidates, HEADER_GATE_MODE)
    candidates_by_chunk: Dict[str, List[HeaderCandidate]] = {}
    for candidate in candidates:
        candidates_by_chunk.setdefault(candidate.chunk_id, []).append(candidate)
    for cand_list in candidates_by_chunk.values():
        cand_list.sort(key=lambda c: (not c.promoted, c.line_index, c.start_char))
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
    domain_hint = (
        decomp.get("metadata", {}).get("domain")
        or decomp.get("metadata", {}).get("domain_hint")
        or decomp.get("domain")
    )
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
        domain=domain_hint,
    )

    seed_candidates = select_quantile_ids(start_scores, DEFAULT_SEED_QUANTILE)
    chunk_lookup = {chunk.id: chunk for chunk in uf_chunks}
    seed_ids = [cid for cid in seed_candidates if chunk_lookup.get(cid) and chunk_lookup[cid].header_anchor]
    if not seed_ids:
        seed_ids = [chunk.id for chunk in uf_chunks if chunk.header_anchor]

    promoted_seed_ids = [
        cid
        for cid, cand_list in candidates_by_chunk.items()
        if cand_list and cand_list[0].promoted
    ]
    ordered = promoted_seed_ids + seed_ids
    seen: Set[str] = set()
    seed_ids = []
    for cid in ordered:
        if cid in chunk_lookup and cid not in seen:
            seed_ids.append(cid)
            seen.add(cid)

    span_records: List[SpanRecord] = []

    for seed_id in seed_ids:
        span = grow_span_from_seed(seed_id, uf_chunks, edges, stop_scores)
        span = snap_and_trim(span, header_ctx, chunk_lookup)
        candidate_list = candidates_by_chunk.get(seed_id, [])
        candidate = candidate_list[0] if candidate_list else None
        hep_detail = score_span_hep(span, chunk_lookup)
        graph_score, graph_penalties = score_graph(span, header_ctx, chunk_lookup)
        final_score = hep_detail["S_HEP"] + span.flow_total - sum(graph_penalties.values())
        promotion_reason = candidate.promotion_reason if candidate and candidate.promoted else None
        accepted = bool(promotion_reason)
        decision = "promoted" if promotion_reason else "rejected"
        if not accepted and HEADER_GATE_MODE == "score_gate":
            if hep_detail["S_HEP"] >= HEP_DEFAULTS["theta_hep"] and final_score >= GRAPH_DEFAULTS["theta_final"]:
                accepted = True
                decision = "accepted"
        record = SpanRecord(
            seed_id=seed_id,
            span=span,
            candidate=candidate,
            hep=hep_detail,
            graph_score=graph_score,
            graph_penalties=graph_penalties,
            start_score=start_scores.get(seed_id, 0.0),
            stop_score=stop_scores.get(span.chunk_ids[-1], 0.0),
            final_score=final_score,
            decision=decision,
            accepted=accepted,
            promotion_reason=promotion_reason,
        )
        span_records.append(record)

    llm_labels = {header.label for header in repaired_headers.headers}
    if span_records:
        _resolve_conflicts(span_records, llm_labels)

    spans_audit = [
        _span_to_audit(
            record.span,
            start_scores,
            stop_scores,
            record.hep,
            record.graph_score,
            record.graph_penalties,
            record.decision,
        )
        for record in span_records
    ]

    accepted_records = [record for record in span_records if record.accepted]

    final_headers_map: Dict[str, VerifiedHeader] = {header.label: header for header in repaired_headers.headers}
    for record in accepted_records:
        span = record.span
        candidate = record.candidate
        label = _extract_label(span.text)
        if candidate and candidate.label:
            label = candidate.label
        if not label:
            continue
        existing = final_headers_map.get(label)
        if existing and existing.source == "repair":
            continue
        if candidate:
            remainder = candidate.text[len(candidate.label) :].lstrip("—-: \u2014 ").strip()
            canonical_text = remainder or span.text.split(label, 1)[-1].strip()
            span_range = (candidate.start_char, max(candidate.end_char, candidate.start_char + len(canonical_text)))
        else:
            canonical_text = span.text.split(label, 1)[-1].strip()
            span_range = span.span
        verification = {"status": "efhg"}
        if record.promotion_reason:
            verification["promotion_reason"] = record.promotion_reason
        source = "pattern" if record.promotion_reason else "efhg"
        confidence = 0.95 if record.promotion_reason == "pattern" else 0.9
        final_headers_map[label] = VerifiedHeader(
            label=label,
            text=canonical_text,
            page=span.page,
            span=span_range,
            verification=verification,
            source=source,
            confidence=confidence,
        )

    if llm_error and not final_headers_map:
        for record in accepted_records:
            span = record.span
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
            "span_char": header.span,
            "verification": header.verification,
            "source": header.source,
            "confidence": header.confidence,
        }
        for header in final_headers
    ]

    accepted_spans = [record.span for record in accepted_records]
    header_shards_payload = _build_header_shards(final_headers, accepted_spans, chunk_lookup)

    uf_records = [
        {
            "id": chunk.id,
            "page": chunk.page,
            "span": chunk.span_char,
            "span_char": chunk.span_char,
            "span_bbox": chunk.span_bbox,
            "text": chunk.text,
            "style": chunk.style,
            "lex": chunk.lex,
            "entropy": chunk.entropy,
            "header_anchor": chunk.header_anchor,
            "domain_hint": chunk.domain_hint,
        }
        for chunk in uf_chunks
    ]

    efhg_records = spans_audit

    raw_candidate_payload = [candidate.to_dict() for candidate in candidates]
    promoted_payload = [
        {
            "candidate_id": record.candidate.candidate_id if record.candidate else None,
            "text": record.candidate.text if record.candidate else record.span.text,
            "page": record.span.page,
            "idx": record.candidate.line_index if record.candidate else None,
            "pattern": record.candidate.pattern if record.candidate else None,
            "promotion_reason": record.promotion_reason,
            "stitched_span": {
                "uf_start": record.span.chunk_ids[0],
                "uf_end": record.span.chunk_ids[-1],
            },
            "efhg": {
                "E": {"start": record.start_score, "stop": record.stop_score},
                "F": {"flow": record.span.flow_total},
                "H": record.hep,
                "G": {"score": record.graph_score, "penalties": record.graph_penalties},
            },
            "conflicts_resolved": list(record.conflicts_resolved),
        }
        for record in accepted_records
        if record.promotion_reason
    ]
    suppressed_payload = [
        {
            "candidate_id": record.candidate.candidate_id if record.candidate else None,
            "pattern": record.candidate.pattern if record.candidate else None,
            "page": record.span.page,
            "reason": record.suppression_reason,
        }
        for record in span_records
        if record.suppression_reason
    ]
    summary_rows = [
        {
            "page": record.span.page,
            "idx": record.candidate.line_index if record.candidate else -1,
            "pattern": record.candidate.pattern if record.candidate else "",
            "decision": record.decision,
            "reason": (
                record.promotion_reason
                if record.promotion_reason
                else json.dumps(record.suppression_reason)
                if record.suppression_reason
                else ""
            ),
        }
        for record in span_records
    ]

    audit_payload = {
        "config": {
            "uf_max_tokens": 90,
            "uf_overlap": 12,
            "entropy": {
                "weights": dict(DEFAULT_WEIGHTS),
                "seed_quantile": DEFAULT_SEED_QUANTILE,
                "stop_quantile": DEFAULT_STOP_QUANTILE,
            },
            "fluid": FLUID_DEFAULTS,
            "hep": HEP_DEFAULTS,
            "graph": GRAPH_DEFAULTS,
            "domain_hint": domain_hint,
            "header_gate_mode": HEADER_GATE_MODE,
            "strict_conflict_only": STRICT_CONFLICT_ONLY,
        },
        "uf_chunks": [
            {
                "id": chunk.id,
                "page": chunk.page,
                "span": chunk.span_char,
                "span_char": chunk.span_char,
                "span_bbox": chunk.span_bbox,
                "text_preview": chunk.preview(),
                "style": chunk.style,
                "lex": chunk.lex,
                "entropy": chunk.entropy,
                "header_anchor": chunk.header_anchor,
                "domain_hint": chunk.domain_hint,
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
        "header_shards": header_shards_payload,
    }

    with (output_dir / "header_candidates_raw.json").open("w", encoding="utf-8") as handle:
        json.dump(raw_candidate_payload, handle, ensure_ascii=False, indent=2)
    with (output_dir / "headers_promoted.json").open("w", encoding="utf-8") as handle:
        json.dump(promoted_payload, handle, ensure_ascii=False, indent=2)
    with (output_dir / "headers_suppressed.json").open("w", encoding="utf-8") as handle:
        json.dump(suppressed_payload, handle, ensure_ascii=False, indent=2)
    with (output_dir / "headers_summary.tsv").open("w", encoding="utf-8") as handle:
        handle.write("page\tidx\tpattern\tdecision\treason\n")
        for row in summary_rows:
            handle.write(
                f"{row['page']}\t{row['idx']}\t{row['pattern']}\t{row['decision']}\t{row['reason']}\n"
            )

    _persist_jsonl(output_dir / "uf_chunks.jsonl", uf_records)
    _persist_jsonl(output_dir / "efhg_spans.jsonl", efhg_records)
    with (output_dir / "headers.json").open("w", encoding="utf-8") as handle:
        json.dump(headers_payload, handle, ensure_ascii=False, indent=2)
    with (output_dir / "header_shards.json").open("w", encoding="utf-8") as handle:
        json.dump(header_shards_payload, handle, ensure_ascii=False, indent=2)
    with (output_dir / "candidate_audit.json").open("w", encoding="utf-8") as handle:
        json.dump(audit_payload, handle, ensure_ascii=False, indent=2)

    return HeaderIndex(
        doc_id=doc_id,
        headers=headers_payload,
        uf_chunks=uf_chunks,
        spans=efhg_records,
        header_shards=header_shards_payload,
        output_dir=output_dir,
    )


__all__ = ["run_headers", "HeaderIndex"]
