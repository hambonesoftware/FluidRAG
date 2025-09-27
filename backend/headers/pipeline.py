from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from collections.abc import Iterable as IterableABC, Mapping as MappingABC
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

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
from backend.headers import config as cfg
from backend.headers.header_finalize import finalize_headers_preprocess_only
from backend.headers.gap_probe import GapProbeLogger
from backend.headers.header_llm import (
    VerifiedHeader,
    VerifiedHeaders,
    aggressive_sequence_repair,
    build_header_prompt,
    call_llm,
    parse_fenced_outline,
    verify_headers,
)
from backend.headers.header_scan import (
    STRONG_PATTERNS,
    HeaderCandidate,
    promote_candidates,
    scan_candidates,
)
from backend.uf_chunker import HEADER_PATTERN, UFChunk, uf_chunk


@dataclass
class HeaderIndex:
    doc_id: str
    headers: List[Dict[str, Any]]
    uf_chunks: List[UFChunk]
    spans: List[Dict[str, Any]]
    header_shards: List[Dict[str, Any]]
    output_dir: Path
    truth: List[Dict[str, Any]] = field(default_factory=list)


class _ArtifactAdapter:
    """Minimal artifact writer used in preprocess-only mode."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def write_json(self, name: str, payload: Mapping[str, Any]) -> Path:
        path = self.base_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return path

    def write_text(self, name: str, text: str) -> Path:
        path = self.base_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class _DocProxy(SimpleNamespace):
    """Adapter that exposes preprocess headers + artifact writers."""

    def __init__(self, doc_id: str, decomp: Mapping[str, Any], output_dir: Path) -> None:
        preprocess_payload = {}
        if isinstance(decomp, MappingABC):
            preprocess_payload = decomp.get("preprocess") or {}
        headers_by_page = None
        if isinstance(preprocess_payload, MappingABC):
            headers_by_page = (
                preprocess_payload.get("headers_by_page")
                or preprocess_payload.get("headers")
                or preprocess_payload.get("pages")
            )
        super().__init__(
            doc_id=doc_id,
            preprocess=SimpleNamespace(headers_by_page=headers_by_page or []),
            artifacts=_ArtifactAdapter(output_dir),
        )


@dataclass
class PreprocessHeader:
    """Normalized representation of a preprocess header entry."""

    id: int
    page: int
    line_idx: Optional[int]
    raw_text: str
    label: Optional[str]
    body: str
    section_number: Optional[str]
    meta: Dict[str, Any]


_PATTERN_PRIORITY = {
    "appendix_top": 4,
    "numeric_section": 3,
    "appendix_sub_AN": 2,
    "appendix_sub_AlN": 2,
}


def _normalize_label_key(label: Optional[str]) -> str:
    if not label:
        return ""
    return re.sub(r"[^0-9A-Za-z]+", "", label).upper()


def _split_label_text(text: str, fallback: Optional[str] = None) -> Tuple[Optional[str], str]:
    cleaned = (text or "").strip()
    if not cleaned and fallback:
        return fallback, ""
    match = HEADER_PATTERN.match(cleaned)
    if match:
        label = match.group(0).strip()
        remainder = cleaned[len(match.group(0)) :].lstrip("—-: \u2014 ").strip()
        return label, remainder
    if fallback:
        return fallback.strip(), cleaned
    return None, cleaned


def _coerce_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def _iter_preprocess_blocks(decomp: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    """Yield page/header blocks from common preprocess payload shapes."""

    def _maybe_iter(obj: Any) -> Iterable[Mapping[str, Any]]:
        if isinstance(obj, MappingABC):
            yield obj
        elif isinstance(obj, IterableABC):
            for item in obj:
                if isinstance(item, MappingABC):
                    yield item

    preprocess = decomp.get("preprocess") if isinstance(decomp, MappingABC) else None
    if isinstance(preprocess, MappingABC):
        for key in ("headers", "headers_by_page", "pages"):
            value = preprocess.get(key)
            if value:
                yield from _maybe_iter(value)
    for key in ("preprocess_headers", "headers", "headers_by_page", "header_pages"):
        value = decomp.get(key)
        if value:
            yield from _maybe_iter(value)


def _load_preprocess_headers(decomp: Mapping[str, Any]) -> List[PreprocessHeader]:
    headers: List[PreprocessHeader] = []
    seen_ids: Set[Tuple[int, Optional[int], str]] = set()
    counter = 0
    for block in _iter_preprocess_blocks(decomp):
        page_raw = block.get("page")
        page = _coerce_int(page_raw) or 0
        entries = block.get("headers") if isinstance(block, MappingABC) else None
        if not page or not isinstance(entries, IterableABC):
            continue
        for entry in entries:
            if not isinstance(entry, MappingABC):
                continue
            raw_text = str(entry.get("text") or entry.get("name") or "").strip()
            if not raw_text:
                continue
            line_idx = _coerce_int(entry.get("line_idx"))
            section_number = entry.get("section_number")
            label, body = _split_label_text(raw_text, str(section_number or "") or None)
            dedupe_key = (page, line_idx, raw_text)
            if dedupe_key in seen_ids:
                continue
            seen_ids.add(dedupe_key)
            headers.append(
                PreprocessHeader(
                    id=counter,
                    page=page,
                    line_idx=line_idx,
                    raw_text=raw_text,
                    label=label,
                    body=body,
                    section_number=str(section_number).strip() if section_number else None,
                    meta=dict(entry),
                )
            )
            counter += 1
    headers.sort(key=lambda h: (h.page, h.line_idx if h.line_idx is not None else 10**6, h.raw_text))
    return headers


def _verified_from_preprocess(
    preprocess_headers: List[PreprocessHeader],
    pages_norm: List[str],
    pages_raw: List[str],
) -> VerifiedHeaders:
    payload_entries: List[Dict[str, Any]] = []
    lookup: Dict[Tuple[int, str, str], PreprocessHeader] = {}
    for header in preprocess_headers:
        label = header.label or header.section_number or header.raw_text
        if not label:
            continue
        body = header.body if header.body else ""
        payload_entries.append({"label": label, "text": body, "page": header.page})
        lookup[(header.page, label, body)] = header

    verified = verify_headers({"headers": payload_entries}, pages_norm, pages_raw)
    results: List[VerifiedHeader] = []
    matched_ids: Set[int] = set()
    for header in verified.headers:
        key = (header.page, header.label, header.text)
        entry = lookup.get(key)
        if entry is None:
            norm_label = _normalize_label_key(header.label)
            candidates = [
                item
                for item in preprocess_headers
                if item.page == header.page and _normalize_label_key(item.label or item.section_number) == norm_label
            ]
            entry = candidates[0] if candidates else None
        if entry is None:
            continue
        matched_ids.add(entry.id)
        verification = dict(header.verification)
        verification.update(
            {
                "status": verification.get("status", "preprocess"),
                "source": "preprocess",
                "preprocess_id": entry.id,
                "line_idx": entry.line_idx,
                "raw_text": entry.raw_text,
            }
        )
        results.append(
            VerifiedHeader(
                label=header.label,
                text=header.text,
                page=header.page,
                span=header.span,
                verification=verification,
                source="preprocess",
                confidence=max(header.confidence, 0.95),
            )
        )

    for entry in preprocess_headers:
        if entry.id in matched_ids:
            continue
        label = entry.label or entry.section_number or entry.raw_text
        if not label:
            continue
        verification = {
            "status": "preprocess_only",
            "source": "preprocess",
            "preprocess_id": entry.id,
            "line_idx": entry.line_idx,
            "raw_text": entry.raw_text,
        }
        span_start = entry.line_idx if entry.line_idx is not None else 0
        results.append(
            VerifiedHeader(
                label=label,
                text=entry.body,
                page=entry.page,
                span=(span_start, span_start),
                verification=verification,
                source="preprocess",
                confidence=0.9,
            )
        )

    results.sort(key=lambda h: (h.page, h.verification.get("line_idx", h.span[0] if h.span else 0), h.label))
    return VerifiedHeaders(headers=results)


def _promote_preprocess_truth(
    candidates: List[HeaderCandidate],
    uf_chunks: List[UFChunk],
    preprocess_headers: List[PreprocessHeader],
    chunk_lookup: Mapping[str, UFChunk],
) -> Dict[int, Dict[str, Any]]:
    for candidate in candidates:
        candidate.promoted = False
        candidate.promotion_reason = None

    candidates_by_chunk: Dict[str, List[HeaderCandidate]] = {}
    for candidate in candidates:
        candidates_by_chunk.setdefault(candidate.chunk_id, []).append(candidate)

    headers_by_line: Dict[Tuple[int, int], List[PreprocessHeader]] = {}
    headers_by_label: Dict[Tuple[int, str], List[PreprocessHeader]] = {}
    for header in preprocess_headers:
        if header.line_idx is not None:
            headers_by_line.setdefault((header.page, header.line_idx), []).append(header)
        key = _normalize_label_key(header.label or header.section_number)
        if key:
            headers_by_label.setdefault((header.page, key), []).append(header)

    matches: Dict[int, Dict[str, Any]] = {}
    for candidate in candidates:
        header: Optional[PreprocessHeader] = None
        line_key = (candidate.page, candidate.line_index)
        candidates_for_line = headers_by_line.get(line_key)
        if candidates_for_line:
            header = candidates_for_line.pop(0)
            if not candidates_for_line:
                headers_by_line.pop(line_key, None)
        if header is None:
            label_key = _normalize_label_key(candidate.label)
            label_candidates = headers_by_label.get((candidate.page, label_key))
            if label_candidates:
                header = label_candidates.pop(0)
                if not label_candidates:
                    headers_by_label.pop((candidate.page, label_key), None)
        if header is None:
            continue
        candidate.promoted = True
        candidate.promotion_reason = "preprocess"
        chunk = chunk_lookup.get(candidate.chunk_id)
        matches[header.id] = {
            "candidate": candidate,
            "uf_anchor": bool(chunk.header_anchor) if chunk else False,
        }

    uf_promotions = _collect_uf_anchor_candidates(candidates_by_chunk, uf_chunks)
    for candidate, source in uf_promotions:
        if not candidate.promoted:
            candidate.promoted = True
            candidate.promotion_reason = source

    return matches


def _apply_preprocess_matches(
    verified_headers: VerifiedHeaders,
    preprocess_headers: List[PreprocessHeader],
    matches: Mapping[int, Dict[str, Any]],
) -> None:
    header_by_id = {header.id: header for header in preprocess_headers}
    for header in verified_headers.headers:
        verification = dict(header.verification)
        preprocess_id = verification.get("preprocess_id")
        if isinstance(preprocess_id, int) and preprocess_id in matches:
            match_info = matches[preprocess_id]
            candidate = match_info.get("candidate")
            if candidate:
                remainder = candidate.text[len(candidate.label) :].lstrip("—-: \u2014 ").strip()
                header.span = (candidate.start_char, max(candidate.end_char, candidate.start_char + len(remainder or header.text)))
                if remainder:
                    header.text = remainder
                verification["promotion_reason"] = "preprocess"
                verification["candidate_id"] = candidate.candidate_id
                verification["chunk_id"] = candidate.chunk_id
            verification["uf_anchor"] = match_info.get("uf_anchor", False)
        else:
            verification.setdefault("uf_anchor", False)
        if isinstance(preprocess_id, int) and preprocess_id in header_by_id:
            entry = header_by_id[preprocess_id]
            verification.setdefault("line_idx", entry.line_idx)
            verification.setdefault("raw_text", entry.raw_text)
        header.verification = verification
        header.source = "preprocess"
        header.confidence = max(header.confidence, 0.95)


def _build_truth_rows(final_headers: List[VerifiedHeader]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for header in final_headers:
        verification = header.verification or {}
        if (verification.get("source") or header.source) != "preprocess":
            continue
        raw_text = str(verification.get("raw_text") or f"{header.label} {header.text}".strip())
        line_idx_raw = verification.get("line_idx")
        try:
            line_idx = int(line_idx_raw)
        except Exception:
            line_idx = 0
        rows.append(
            {
                "page": int(header.page),
                "line_idx": line_idx,
                "text": raw_text,
                "provenance": {
                    "preprocess": True,
                    "uf_anchor": bool(verification.get("uf_anchor")),
                },
            }
        )
    rows.sort(key=lambda row: (row["page"], row["line_idx"], row["text"]))
    return rows


def _write_truth_rows(output_dir: Path, rows: List[Dict[str, Any]]) -> None:
    payload = {"headers_final": rows}
    with (output_dir / "headers_final.json").open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


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
    demotion_reason: str | None = None


def _pattern_rank(record: SpanRecord) -> int:
    if record.candidate:
        return _PATTERN_PRIORITY.get(record.candidate.pattern, 1)
    return 1


def _record_pattern(record: SpanRecord) -> str | None:
    if record.candidate and record.candidate.pattern:
        return record.candidate.pattern
    return _classify_pattern(_extract_label(record.span.text))


def _record_family(record: SpanRecord) -> str:
    pattern = _record_pattern(record) or ""
    if pattern.startswith("appendix"):
        return "appendix"
    if pattern == "numeric_section":
        return "numeric"
    return "general"


def _classify_pattern(label: str | None) -> str | None:
    if not label:
        return None
    cleaned = label.strip()
    if not cleaned:
        return None
    if re.match(r"^\d+\)$", cleaned):
        return "numeric_section"
    if re.match(r"(?i)^(appendix|annex)\s+[A-Z]\b", cleaned):
        return "appendix_top"
    if re.match(r"^[A-Z]\d{1,3}\.$", cleaned):
        return "appendix_sub_AN"
    if re.match(r"^[A-Z]\.\d{1,3}$", cleaned):
        return "appendix_sub_AlN"
    return None


def _normalize_candidate_text(candidate: HeaderCandidate) -> str:
    base = candidate.text or candidate.label or ""
    return re.sub(r"\s+", " ", base).strip().lower()


def _normalize_and_merge(
    proposals: List[Tuple[HeaderCandidate, str]]
) -> List[Tuple[HeaderCandidate, str]]:
    """Collapse duplicate promotions that share text within a local span."""

    selected: List[Tuple[HeaderCandidate, str]] = []
    for candidate, source in proposals:
        norm_text = _normalize_candidate_text(candidate)
        matched_index: int | None = None
        for idx, (existing, existing_source) in enumerate(selected):
            if existing.page != candidate.page:
                continue
            if _normalize_candidate_text(existing) != norm_text:
                continue
            if abs(existing.start_char - candidate.start_char) <= 40:
                matched_index = idx
                # Prefer UF anchors when both sources agree so that the
                # downstream stitching logic keeps the stronger anchor.
                if existing_source != "uf_anchor" and source == "uf_anchor":
                    selected[idx] = (candidate, source)
                break
        if matched_index is None:
            selected.append((candidate, source))
    return selected


def _collect_uf_anchor_candidates(
    candidates_by_chunk: Dict[str, List[HeaderCandidate]],
    uf_chunks: List[UFChunk],
) -> List[Tuple[HeaderCandidate, str]]:
    uf_promotions: List[Tuple[HeaderCandidate, str]] = []
    for chunk in uf_chunks:
        if not chunk.header_anchor:
            continue
        cand_list = candidates_by_chunk.get(chunk.id)
        if not cand_list:
            continue
        uf_promotions.append((cand_list[0], "uf_anchor"))
    return uf_promotions


def _collect_llm_candidates(
    candidates: List[HeaderCandidate], llm_headers: VerifiedHeaders
) -> List[Tuple[HeaderCandidate, str]]:
    llm_labels = {header.label for header in llm_headers.headers}
    llm_promotions: List[Tuple[HeaderCandidate, str]] = []
    if not llm_labels:
        return llm_promotions
    for candidate in candidates:
        if candidate.label and candidate.label in llm_labels:
            llm_promotions.append((candidate, "llm"))
    return llm_promotions


def _promote_raw_truth(
    candidates: List[HeaderCandidate],
    uf_chunks: List[UFChunk],
    llm_headers: VerifiedHeaders,
) -> List[HeaderCandidate]:
    """Promote the union of UF anchors and LLM headers without score gating."""

    for candidate in candidates:
        candidate.promoted = False
        candidate.promotion_reason = None

    candidates_by_chunk: Dict[str, List[HeaderCandidate]] = {}
    for candidate in candidates:
        candidates_by_chunk.setdefault(candidate.chunk_id, []).append(candidate)

    proposals: List[Tuple[HeaderCandidate, str]] = []
    # 1) Gather what already works: UF anchors and LLM labels.
    proposals.extend(_collect_uf_anchor_candidates(candidates_by_chunk, uf_chunks))
    proposals.extend(_collect_llm_candidates(candidates, llm_headers))

    # 2) Normalize + de-dupe (same text, nearby span → one item).
    merged = _normalize_and_merge(proposals)

    # 3) Promote everything in the merged list.
    for candidate, source in merged:
        candidate.promoted = True
        if candidate.pattern in STRONG_PATTERNS:
            candidate.promotion_reason = "pattern"
        else:
            candidate.promotion_reason = source

    return [candidate for candidate, _ in merged]


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


def _ignore_conflict(record: SpanRecord, winner: SpanRecord) -> bool:
    family = _record_family(record)
    winner_family = _record_family(winner)
    if "appendix" in {family, winner_family} and family != winner_family:
        return True
    if record.promotion_reason and winner.promotion_reason:
        cand = record.candidate
        win_cand = winner.candidate
        if (
            cand
            and win_cand
            and cand.chunk_id == win_cand.chunk_id
            and cand.line_index != win_cand.line_index
        ):
            return True
    return False


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
        record.demotion_reason = None

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
            if _ignore_conflict(record, winner):
                continue
            overlap = _span_overlap(winner, record)
            if overlap <= 0:
                continue
            has_conflict = True
            record.accepted = False
            record.decision = "conflict_suppressed"
            loser_label = record.candidate.label if record.candidate else _extract_label(record.span.text)
            winner_label = winner.candidate.label if winner.candidate else _extract_label(winner.span.text)
            record_family = _record_family(record)
            winner_family = _record_family(winner)
            if record_family == "appendix" and winner_family != "appendix":
                demotion_reason = "conflict_with_numeric"
            elif record_family == winner_family:
                demotion_reason = "span_collision"
            else:
                demotion_reason = "conflict"
            record.suppression_reason = {
                "reason": "span_collision",
                "winner": winner_label,
                "overlap": overlap,
            }
            record.demotion_reason = demotion_reason
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
    demotion_reason: str | None,
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
        "demotion_reason": demotion_reason,
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
    output_dir = _ensure_output_dir(doc_id, decomp.get("output_dir"))

    if cfg.HEADER_MODE == "preprocess_only":
        doc_proxy = _DocProxy(doc_id, decomp, output_dir)
        final_headers = finalize_headers_preprocess_only(doc_proxy)
        truth_rows = [
            {
                "page": entry["page"],
                "line_idx": entry.get("line_idx"),
                "text": entry["text"],
                "provenance": "preprocess",
            }
            for entry in final_headers
        ]
        headers_payload = [
            {
                "label": entry["text"],
                "text": entry["text"],
                "page": entry["page"],
                "span": None,
                "source": "preprocess",
                "confidence": 1.0,
            }
            for entry in final_headers
        ]
        return HeaderIndex(
            doc_id=doc_id,
            headers=headers_payload,
            uf_chunks=[],
            spans=[],
            header_shards=[],
            output_dir=output_dir,
            truth=truth_rows,
        )

    assert (
        cfg.HEADER_MODE != "preprocess_only"
    ), "Post-process must not run in preprocess_only mode"

    pages = decomp.get("pages", [])
    pages_norm = [page.get("text", "") for page in pages]
    pages_raw = [page.get("raw_text", page.get("text", "")) for page in pages]
    tokens_per_page = [page.get("tokens", []) for page in pages]

    uf_chunks = uf_chunk(decomp)
    chunk_lookup = {chunk.id: chunk for chunk in uf_chunks}
    legacy_profile = getattr(cfg, "HEADER_LEGACY_PROFILE", "preprocess_truth")
    legacy_mode = cfg.HEADER_MODE == "legacy"
    preprocess_truth_active = legacy_mode and legacy_profile == "preprocess_truth"
    raw_truth_active = legacy_mode and legacy_profile == "raw_truth"
    preprocess_headers = _load_preprocess_headers(decomp) if preprocess_truth_active else []
    preprocess_matches: Dict[int, Dict[str, Any]] = {}
    candidates = scan_candidates(uf_chunks)
    compute_entropy_features(uf_chunks)
    start_scores = score_starts(uf_chunks)
    stop_scores = score_stops(uf_chunks)
    edges = build_edges(uf_chunks)

    gap_logger = GapProbeLogger(
        doc_id,
        pages_raw,
        pages_norm,
        tokens_per_page,
        uf_chunks,
        start_scores,
        stop_scores,
        candidates,
    )

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
    if preprocess_truth_active and preprocess_headers:
        preprocess_verified = _verified_from_preprocess(preprocess_headers, pages_norm, pages_raw)
        if preprocess_verified.headers:
            repaired_headers = preprocess_verified
    if preprocess_truth_active:
        preprocess_matches = _promote_preprocess_truth(candidates, uf_chunks, preprocess_headers, chunk_lookup)
    elif raw_truth_active:
        _promote_raw_truth(candidates, uf_chunks, verified_headers)
    else:
        promote_candidates(candidates, cfg.HEADER_GATE_MODE)
    candidates_by_chunk: Dict[str, List[HeaderCandidate]] = {}
    for candidate in candidates:
        candidates_by_chunk.setdefault(candidate.chunk_id, []).append(candidate)
    for cand_list in candidates_by_chunk.values():
        cand_list.sort(key=lambda c: (not c.promoted, c.line_index, c.start_char))
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
        if (
            not accepted
            and not raw_truth_active
            and cfg.HEADER_GATE_MODE == "score_gate"
        ):
            if hep_detail["S_HEP"] >= HEP_DEFAULTS["theta_hep"] and final_score >= GRAPH_DEFAULTS["theta_final"]:
                accepted = True
                decision = "accepted"
        demotion_reason = None
        if not accepted:
            if not raw_truth_active and cfg.HEADER_GATE_MODE == "score_gate":
                demotion_reason = "score_gate"
            else:
                demotion_reason = "not_promoted"
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
            demotion_reason=demotion_reason,
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
            record.demotion_reason,
        )
        for record in span_records
    ]

    accepted_records = [record for record in span_records if record.accepted]

    if preprocess_truth_active and preprocess_headers:
        _apply_preprocess_matches(repaired_headers, preprocess_headers, preprocess_matches)

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
        if (
            preprocess_truth_active
            and existing
            and record.promotion_reason == "preprocess"
        ):
            verification = dict(existing.verification)
            verification.update({"status": "efhg", "promotion_reason": record.promotion_reason})
            if candidate:
                remainder = candidate.text[len(candidate.label) :].lstrip("—-: \u2014 ").strip()
                canonical_text = remainder or existing.text or span.text.split(label, 1)[-1].strip()
                span_range = (candidate.start_char, max(candidate.end_char, candidate.start_char + len(canonical_text)))
            else:
                canonical_text = existing.text or span.text.split(label, 1)[-1].strip()
                span_range = span.span
            verification.setdefault("uf_anchor", existing.verification.get("uf_anchor", False))
            verification.setdefault("preprocess_id", existing.verification.get("preprocess_id"))
            existing.text = canonical_text
            existing.span = span_range
            existing.verification = verification
            existing.source = "preprocess"
            existing.confidence = max(existing.confidence, 0.97)
            final_headers_map[label] = existing
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
        source = record.promotion_reason or "efhg"
        if record.promotion_reason == "uf_anchor":
            confidence = 0.95
        elif record.promotion_reason == "llm":
            confidence = 0.9
        else:
            confidence = 0.9 if record.promotion_reason else 0.9
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

    truth_rows: List[Dict[str, Any]] = []
    if preprocess_truth_active:
        truth_rows = _build_truth_rows(final_headers)
        _write_truth_rows(output_dir, truth_rows)

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

    gap_logger.detect_gaps(headers_payload)

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
    promoted_payload: List[Dict[str, Any]] = []
    for record in accepted_records:
        if not record.promotion_reason:
            continue
        promoted_payload.append(
            {
                "candidate_id": record.candidate.candidate_id if record.candidate else None,
                "text": record.candidate.text if record.candidate else record.span.text,
                "page": record.span.page,
                "idx": record.candidate.line_index if record.candidate else None,
                "pattern": record.candidate.pattern if record.candidate else _classify_pattern(_extract_label(record.span.text)),
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
        )

    repair_lookup: Dict[Tuple[str, int, Tuple[int, int]], Dict[str, Any]] = {}
    for entry in repaired_headers.repair_log:
        series = entry.get("series")
        gap = entry.get("gap")
        for result in entry.get("result", []):
            label = result.get("label")
            page = int(result.get("page", 0) or 0)
            span_raw = result.get("span")
            if isinstance(span_raw, (list, tuple)) and len(span_raw) == 2:
                span_tuple = (int(span_raw[0]), int(span_raw[1]))
            else:
                span_tuple = (0, 0)
            repair_lookup[(label, page, span_tuple)] = {
                "series": series,
                "gap": gap,
                "method": result.get("method"),
                "confidence": result.get("confidence"),
            }

    for header in repaired_headers.headers:
        if header.source != "repair":
            continue
        key = (header.label, header.page, tuple(header.span))
        repair_meta = repair_lookup.get(key, {})
        promoted_payload.append(
            {
                "candidate_id": None,
                "text": header.text,
                "page": header.page,
                "idx": -1,
                "pattern": _classify_pattern(header.label),
                "promotion_reason": "sequence_repair",
                "stitched_span": {"uf_start": None, "uf_end": None},
                "efhg": {"E": {}, "F": {}, "H": {}, "G": {}},
                "conflicts_resolved": [],
                "repair": repair_meta,
            }
        )
    suppressed_payload = [
        {
            "candidate_id": record.candidate.candidate_id if record.candidate else None,
            "pattern": record.candidate.pattern if record.candidate else None,
            "page": record.span.page,
            "reason": record.suppression_reason,
            "demotion_reason": record.demotion_reason,
        }
        for record in span_records
        if record.suppression_reason
    ]
    summary_rows: List[Dict[str, Any]] = []
    for record in span_records:
        if record.promotion_reason:
            reason = record.promotion_reason
        elif record.suppression_reason:
            reason = json.dumps(record.suppression_reason)
        else:
            reason = ""
        summary_rows.append(
            {
                "page": record.span.page,
                "idx": record.candidate.line_index if record.candidate else -1,
                "pattern": record.candidate.pattern if record.candidate else _classify_pattern(_extract_label(record.span.text)) or "",
                "decision": record.decision,
                "reason": reason,
                "demotion_reason": record.demotion_reason or "",
            }
        )

    for header in repaired_headers.headers:
        if header.source != "repair":
            continue
        key = (header.label, header.page, tuple(header.span))
        repair_meta = repair_lookup.get(key, {})
        repair_reason_parts = ["sequence_repair"]
        if repair_meta.get("series"):
            repair_reason_parts.append(str(repair_meta["series"]))
        if repair_meta.get("gap"):
            repair_reason_parts.append(str(repair_meta["gap"]))
        repair_reason = "|".join(repair_reason_parts)
        summary_rows.append(
            {
                "page": header.page,
                "idx": -1,
                "pattern": _classify_pattern(header.label) or "",
                "decision": "sequence_repair",
                "reason": repair_reason,
                "demotion_reason": "",
            }
        )

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
            "header_gate_mode": cfg.HEADER_GATE_MODE,
            "header_mode": cfg.HEADER_MODE,
            "strict_conflict_only": cfg.STRICT_CONFLICT_ONLY,
            "legacy_profile": getattr(cfg, "HEADER_LEGACY_PROFILE", None),
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
        "gap_probes": gap_logger.as_list(),
    }
    if preprocess_truth_active:
        audit_payload["headers_final_truth"] = truth_rows

    with (output_dir / "header_candidates_raw.json").open("w", encoding="utf-8") as handle:
        json.dump(raw_candidate_payload, handle, ensure_ascii=False, indent=2)
    with (output_dir / "headers_promoted.json").open("w", encoding="utf-8") as handle:
        json.dump(promoted_payload, handle, ensure_ascii=False, indent=2)
    with (output_dir / "headers_suppressed.json").open("w", encoding="utf-8") as handle:
        json.dump(suppressed_payload, handle, ensure_ascii=False, indent=2)
    with (output_dir / "headers_summary.tsv").open("w", encoding="utf-8") as handle:
        handle.write("page\tidx\tpattern\tdecision\treason\tdemotion_reason\n")
        for row in summary_rows:
            handle.write(
                f"{row['page']}\t{row['idx']}\t{row['pattern']}\t{row['decision']}\t{row['reason']}\t{row['demotion_reason']}\n"
            )

    _persist_jsonl(output_dir / "uf_chunks.jsonl", uf_records)
    _persist_jsonl(output_dir / "efhg_spans.jsonl", efhg_records)
    with (output_dir / "headers.json").open("w", encoding="utf-8") as handle:
        json.dump(headers_payload, handle, ensure_ascii=False, indent=2)
    with (output_dir / "header_shards.json").open("w", encoding="utf-8") as handle:
        json.dump(header_shards_payload, handle, ensure_ascii=False, indent=2)
    gap_logger.write(output_dir)

    with (output_dir / "candidate_audit.json").open("w", encoding="utf-8") as handle:
        json.dump(audit_payload, handle, ensure_ascii=False, indent=2)

    return HeaderIndex(
        doc_id=doc_id,
        headers=headers_payload,
        uf_chunks=uf_chunks,
        spans=efhg_records,
        header_shards=header_shards_payload,
        output_dir=output_dir,
        truth=truth_rows,
    )


def _doc_id_from_obj(doc: object) -> str:
    for attr in ("doc_id", "document_id", "id"):
        value = getattr(doc, attr, None)
        if value:
            return str(value)
    return "document"


def _decomp_from_doc(doc: object) -> Mapping[str, Any]:
    if isinstance(doc, MappingABC):
        return doc
    for attr in ("decomp", "payload", "data"):
        value = getattr(doc, attr, None)
        if isinstance(value, MappingABC):
            return value
    raise AttributeError("Document object does not expose a header decomposition payload")


def run_headers_stage(doc: object) -> List[Dict[str, Any]]:
    """Return the finalized headers list for ``doc`` based on configuration."""

    if cfg.HEADER_MODE == "preprocess_only":
        return finalize_headers_preprocess_only(doc)

    assert (
        cfg.HEADER_MODE != "preprocess_only"
    ), "Post-process must not run in preprocess_only mode"

    doc_id = _doc_id_from_obj(doc)
    decomp = _decomp_from_doc(doc)
    result = run_headers(doc_id, dict(decomp))
    return result.truth


__all__ = ["run_headers", "run_headers_stage", "HeaderIndex"]
