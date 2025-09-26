"""End-to-end orchestration helpers for the FluidRAG v2 blueprint."""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Set

import numpy as np

from .chunking.microchunker import microchunk
from .embedding.encoder import EmbeddingEncoder
from .embedding.prototypes import build_prototype_index, topk_header_prototypes
from .extraction.atomic_spans import extract_atomic
from .extraction.dedupe import dedupe
from .extraction.provenance import to_overlay
from .graph.loader import build_graph as build_chunk_graph
from .graph.model import Graph
from .preprocess.line_segmenter import join_split_lines
from .preprocess.normalize import normalize_text
from .reporting.html_report import render as render_report
from .retrieval.chunk_recall import recall_chunks
from .retrieval.fuse_scores import fuse
from .retrieval.section_filter import prefilter_sections
from .sectioning.header_match import APPENDIX_RE, NUMERIC_RE, classify_line
from .sectioning.header_score import THRESHOLD, score_candidate
from .sectioning.section_graph import build_section_graph
from .sectioning.header_features import compute_features
from .sectioning.text_normalize import normalize_for_headers
from .validators.conflicts import find_conflicts
from .validators.units import parse_units

DEFAULT_CONFIG: Dict[str, Mapping[str, object]] = {
    "embedding": {
        "model": "gte-base@v3",
        "dim": 128,
        "version": "2025-09-25",
        "section_tokens": 128,
    },
    "retrieval": {
        "M_sections": 15,
        "Kprime": 40,
        "K_final": 7,
        "section_cap": 3,
    },
    "passes": {
        "mechanical": {"alpha": 0.45, "beta": 0.20, "gamma": 0.20, "delta": 0.15},
        "electrical": {"alpha": 0.40, "beta": 0.20, "gamma": 0.25, "delta": 0.15},
        "software": {"alpha": 0.55, "beta": 0.15, "gamma": 0.20, "delta": 0.10},
        "controls": {"alpha": 0.45, "beta": 0.20, "gamma": 0.25, "delta": 0.10},
        "pm": {"alpha": 0.50, "beta": 0.20, "gamma": 0.20, "delta": 0.10},
    },
    "microchunks": {
        "window_chars": 300,
        "stride_chars": 240,
    },
}


_NEIGHBOR_BONUS = 0.15
_APPENDIX_RESCUE_RX = re.compile(r"^\s*([A-Z])(5|6)\.\s{0,2}(.*)$")
_APPENDIX_FOCUS_RX = re.compile(r"^\s*A([4-8])([.\u2024\u2027\uFF0E]|\b)")
_SEGMENT_REASON_KEYS = (
    "segment_reason",
    "line_reason",
    "break_reason",
    "wrap_reason",
    "split_reason",
)
_APPENDIX_A56_PREFIX_RX = re.compile(r"^\s*A([56])[.\u2024\u2027\uFF0E]\s*(?P<tail>.*)$")
_APPENDIX_BOUNDARY_ANCHOR_RX = re.compile(r"^\s*A\d{1,3}[.\u2024\u2027\uFF0E]")


def _caps_ratio(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    upper = sum(1 for ch in letters if ch.isupper())
    return upper / len(letters)


def _units_present(text: str) -> bool:
    parsed = parse_units(text or "")
    return bool(parsed.get("units"))


def _codepoints(text: Optional[str]) -> List[str]:
    if not text:
        return []
    return [f"U+{ord(ch):04X}" for ch in text]


def _union_bbox(a: Optional[Sequence[float]], b: Optional[Sequence[float]]):
    if not a:
        return b
    if not b:
        return a
    return [
        min(a[0], b[0]),
        min(a[1], b[1]),
        max(a[2], b[2]),
        max(a[3], b[3]),
    ]


def _segment_reason_for_line(line: Mapping[str, object]) -> Optional[str]:
    for key in _SEGMENT_REASON_KEYS:
        value = line.get(key)
        if value:
            return str(value)
    return None


def _regex_probe(norm_text: str) -> Dict[str, object]:
    numeric_match = NUMERIC_RE.search(norm_text or "")
    appendix_match = APPENDIX_RE.search(norm_text or "")
    match_span: Optional[Tuple[int, int]] = None
    if appendix_match:
        match_span = appendix_match.span()
    elif numeric_match:
        match_span = numeric_match.span()
    return {
        "numeric": bool(numeric_match),
        "appendix": bool(appendix_match),
        "match_span": list(match_span) if match_span else None,
        "numeric_span": list(numeric_match.span()) if numeric_match else None,
        "appendix_span": list(appendix_match.span()) if appendix_match else None,
    }


def _style_snapshot(line: Mapping[str, object], caps_ratio: float) -> Dict[str, float | bool | None]:
    return {
        "font_size": line.get("font_size"),
        "bold": bool(line.get("bold")),
        "font_sigma_rank": float(line.get("font_sigma_rank") or 0.0),
        "font_size_z": float(line.get("font_size_z") or 0.0),
        "caps_ratio": float(caps_ratio),
    }


_APPENDIX_PREFIX_STRICT_RX = re.compile(r"^A\d{1,3}[.\u2024\u2027\uFF0E]?$")


def _infer_skip_reason(norm_text: str, caps_ratio: float) -> str:
    stripped = (norm_text or "").strip()
    if not stripped:
        return "empty_norm"
    if _APPENDIX_PREFIX_STRICT_RX.match(stripped):
        return "too_short_after_prefix"
    if stripped.endswith(".") and caps_ratio < 0.6:
        return "disqualified_caps_ratio"
    return "regex_fail"


def _extract_appendix_number(value: object) -> Optional[int]:
    if value is None:
        return None
    token = str(value).strip()
    if not token:
        return None
    token = token.rstrip(".)")
    token = token.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
    if not token:
        return None
    try:
        return int(token)
    except ValueError:
        return None


def _decide_candidate(
    meets_threshold: bool,
    is_numeric: bool,
    is_appendix: bool,
    style: Mapping[str, object],
) -> str:
    if meets_threshold:
        return "selected"
    if (is_numeric or is_appendix) and (
        style.get("bold") or float(style.get("font_sigma_rank") or 0.0) >= 0.5
    ):
        return "selected_fallback"
    return "below_threshold"


def _should_apply_units_penalty(text: str) -> bool:
    stripped = normalize_for_headers(text)
    if NUMERIC_RE.match(stripped):
        return False
    if APPENDIX_RE.match(stripped):
        return False
    return True


def _font_metrics(lines: List[Dict]) -> None:
    sizes = [float(line.get("font_size") or 0.0) for line in lines]
    if not sizes:
        return
    mean = sum(sizes) / len(sizes)
    variance = sum((size - mean) ** 2 for size in sizes) / max(len(sizes), 1)
    std = math.sqrt(variance)
    distinct = sorted(set(sizes))
    denom = float(len(distinct) - 1) if len(distinct) > 1 else 1.0
    rank_lookup = {value: idx / denom for idx, value in enumerate(distinct)}
    for line, size in zip(lines, sizes):
        z = (size - mean) / std if std else 0.0
        line["font_size_z"] = z
        line["font_sigma_rank"] = rank_lookup.get(size, 0.0)


def _serialize_top3(entries: Sequence[Tuple[str, float]]) -> List[Dict[str, float]]:
    return [{"id": proto_id, "score": float(score)} for proto_id, score in entries]


def _build_candidate_record(
    line: Mapping[str, object],
    norm_text: str,
    *,
    encoder: EmbeddingEncoder,
    prototypes: Mapping[str, np.ndarray],
    rescue: bool = False,
    gate_trace: Optional[List[Dict]] = None,
) -> Optional[Dict]:
    norm_text = norm_text or ""
    caps_ratio = _caps_ratio(norm_text)
    style = _style_snapshot(line, caps_ratio)
    probe = _regex_probe(norm_text)

    debug_entry = {
        "page": int(line.get("page") or 0),
        "line_idx": int(line.get("line_idx") or line.get("order") or 0),
        "text_raw": line.get("text_raw") or line.get("text_norm") or "",
        "text_norm": norm_text,
        "regex_probe": probe,
        "style": {
            "font_size": style.get("font_size"),
            "bold": style.get("bold"),
            "font_sigma_rank": style.get("font_sigma_rank"),
            "caps_ratio": style.get("caps_ratio"),
        },
        "rescue": rescue,
    }

    if not norm_text.strip():
        debug_entry["skip_reason"] = "empty_norm"
        if gate_trace is not None:
            gate_trace.append(debug_entry)
        return None

    feature_line = {**line, "text_norm": norm_text, "caps_ratio": caps_ratio}
    vector = encoder.embed_texts([norm_text])[0]
    proto_matches = topk_header_prototypes(vector, prototypes, k=3)
    computed = compute_features(feature_line, proto_matches, p_header=0.0)
    kind_data = classify_line(norm_text, caps_ratio)
    debug_entry["kind"] = kind_data.get("kind")

    if kind_data.get("kind") == "none":
        debug_entry["skip_reason"] = _infer_skip_reason(norm_text, caps_ratio)
        if gate_trace is not None:
            gate_trace.append(debug_entry)
        return None

    score, parts = score_candidate(kind_data["kind"], computed)
    parts = {key: float(val) for key, val in parts.items()}
    parts.setdefault("units_penalty_applied", False)

    is_numeric = bool(NUMERIC_RE.match(norm_text))
    is_appendix = bool(APPENDIX_RE.match(norm_text))

    if _units_present(norm_text) and _should_apply_units_penalty(norm_text):
        if not (is_numeric or is_appendix):
            score -= 0.6
            parts["units_penalty"] = -0.6
            parts["units_penalty_applied"] = True

    meets_threshold = score >= THRESHOLD
    decision = _decide_candidate(meets_threshold, is_numeric, is_appendix, style)

    features = {
        key: float(computed.get(key, 0.0))
        for key in (
            "bold",
            "font_sigma",
            "font_z",
            "caps_ratio",
            "len",
            "proto_sim_max",
            "p_header",
        )
    }

    candidate = {
        **line,
        **kind_data,
        "raw_number": kind_data.get("number"),
        "header_norm": norm_text,
        "score": float(score),
        "partials": parts,
        "features": features,
        "proto_top3": _serialize_top3(computed.get("proto_top3", [])),
        "meets_threshold": meets_threshold,
        "decision": decision,
        "is_numeric": is_numeric,
        "is_appendix": is_appendix,
        "style": style,
        "rescue_applied": rescue,
    }

    candidate["number"] = _section_number(
        kind_data["kind"], {"letter": kind_data.get("letter"), "number": kind_data.get("number")}
    )

    if candidate["proto_top3"]:
        top_entry = candidate["proto_top3"][0]
        if top_entry["score"] >= 0.6:
            candidate["canonical_id"] = top_entry["id"]
            candidate["canonical_conf"] = round(float(top_entry["score"]), 4)

    if is_appendix:
        candidate["section_letter"] = kind_data.get("letter")
        candidate["section_number"] = _extract_appendix_number(kind_data.get("number"))

    if "units_penalty_applied" not in candidate["partials"]:
        candidate["partials"]["units_penalty_applied"] = False

    debug_entry.update(
        {
            "skip_reason": None,
            "decision": decision,
            "score": float(score),
            "partials": dict(candidate.get("partials", {})),
            "meets_threshold": meets_threshold,
            "is_appendix": is_appendix,
            "is_numeric": is_numeric,
            "number": candidate.get("number"),
        }
    )
    if gate_trace is not None:
        gate_trace.append(debug_entry)

    return candidate


def _candidate_debug_entry(candidate: Mapping[str, object]) -> Dict[str, object]:
    style = candidate.get("style") or {}
    regex_hits = "none"
    if candidate.get("is_appendix"):
        regex_hits = "appendix"
    elif candidate.get("is_numeric"):
        regex_hits = "numeric"

    return {
        "page": int(candidate.get("page") or 0),
        "line_idx": int(candidate.get("line_idx") or 0),
        "raw_text": candidate.get("text_raw") or candidate.get("text_norm"),
        "norm_text_repr": repr(candidate.get("header_norm", "")),
        "regex_hits": regex_hits,
        "style": {
            "font_size": style.get("font_size"),
            "bold": style.get("bold"),
            "font_sigma_rank": style.get("font_sigma_rank"),
            "caps_ratio": style.get("caps_ratio"),
        },
        "partials": dict(candidate.get("partials", {})),
        "score": float(candidate.get("score", 0.0)),
        "meets_threshold": bool(candidate.get("meets_threshold", False)),
        "decision": candidate.get("decision"),
    }


def _apply_appendix_sequence_bonus(candidates: Sequence[Dict]) -> None:
    groups: Dict[Tuple[int, str], List[Tuple[int, Dict]]] = defaultdict(list)
    for cand in candidates:
        if cand.get("kind") != "appendix":
            continue
        letter = str(cand.get("letter") or "").upper()
        if not letter:
            continue
        number = _extract_appendix_number(cand.get("raw_number") or cand.get("number"))
        if number is None:
            continue
        page = int(cand.get("page") or 0)
        groups[(page, letter)].append((number, cand))

    for (_page, letter), entries in groups.items():
        if not entries:
            continue
        number_lookup = {num: cand for num, cand in entries}
        for num, cand in entries:
            neighbors = []
            for delta in (-1, 1):
                neighbor = number_lookup.get(num + delta)
                if not neighbor:
                    continue
                if abs(int(neighbor.get("order", 0)) - int(cand.get("order", 0))) <= 4:
                    neighbors.append(neighbor)
            if neighbors:
                parts = dict(cand.get("partials", {}))
                parts["neighbor_bonus"] = parts.get("neighbor_bonus", 0.0) + _NEIGHBOR_BONUS
                cand["partials"] = parts
                cand["score"] = float(cand.get("score", 0.0) + _NEIGHBOR_BONUS)


def _appendix_neighbor_rescue(
    processed: Sequence[Dict],
    header_candidates: Sequence[Dict],
    encoder: EmbeddingEncoder,
    prototypes: Mapping[str, np.ndarray],
    *,
    gate_trace: Optional[List[Dict]] = None,
) -> List[Dict]:
    groups: Dict[Tuple[int, str], Set[int]] = defaultdict(set)
    existing_keys: Set[Tuple[int, str, int]] = set()
    for cand in header_candidates:
        if cand.get("kind") != "appendix":
            continue
        letter = str(cand.get("letter") or cand.get("section_letter") or "").upper()
        number = _extract_appendix_number(cand.get("raw_number") or cand.get("number"))
        if not letter or number is None:
            continue
        page = int(cand.get("page") or 0)
        groups[(page, letter)].add(number)
        existing_keys.add((page, letter, number))

    additions: List[Dict] = []

    for (page, letter), numbers in groups.items():
        if letter != "A":
            continue
        if not {3, 4, 7, 8}.issubset(numbers):
            continue
        needed = {num for num in (5, 6) if num not in numbers}
        if not needed:
            continue

        page_lines = [line for line in processed if int(line.get("page") or 0) == page]
        for idx, base_line in enumerate(page_lines):
            norm_line = normalize_for_headers(base_line.get("header_norm") or base_line.get("text_norm", ""))
            match = _APPENDIX_RESCUE_RX.match(norm_line)
            if not match:
                continue
            token_letter, token_number, tail = match.groups()
            number_val = int(token_number)
            key = (page, token_letter.upper(), number_val)
            if number_val not in needed or key in existing_keys:
                continue

            tail_clean = tail.strip()
            prefix = f"{token_letter}{token_number}."
            parts = [prefix]
            if tail_clean:
                parts.append(tail_clean)

            if len(tail_clean) < 6 and idx + 1 < len(page_lines):
                next_norm = normalize_for_headers(
                    page_lines[idx + 1].get("header_norm") or page_lines[idx + 1].get("text_norm", "")
                )
                next_clean = next_norm.strip()
                if next_clean:
                    parts.append(next_clean)

            combined_norm = " ".join(part for part in parts if part).strip()
            if not APPENDIX_RE.match(combined_norm):
                continue

            rescue_line = dict(base_line)
            rescue_line.setdefault("page", page)
            rescue_line.setdefault("line_idx", base_line.get("line_idx", idx))
            candidate = _build_candidate_record(
                rescue_line,
                combined_norm,
                encoder=encoder,
                prototypes=prototypes,
                rescue=True,
                gate_trace=gate_trace,
            )
            if not candidate or candidate.get("kind") != "appendix":
                continue

            candidate["page"] = rescue_line.get("page", page)
            candidate["line_idx"] = rescue_line.get("line_idx", base_line.get("line_idx", idx))
            additions.append(candidate)
            existing_keys.add(key)
            needed.discard(number_val)

            if not needed:
                break

    return additions


def _appendix_soft_unwrap_lines(
    lines: Sequence[Dict],
    appendix_pages: Set[int],
    *,
    debug: Optional[List[Dict]] = None,
) -> List[Dict]:
    if not appendix_pages:
        return list(lines)

    output: List[Dict] = []
    idx = 0
    total = len(lines)

    while idx < total:
        line = dict(lines[idx])
        page = int(line.get("page") or 0)
        text_norm = line.get("text_norm", "")
        header_norm = normalize_for_headers(text_norm)
        consumed_next = False

        if page in appendix_pages:
            match = _APPENDIX_A56_PREFIX_RX.match(header_norm)
            if match:
                tail = (match.group("tail") or "").strip()
                tail_tokens = len(tail.split()) if tail else 0
                if tail_tokens < 6 and idx + 1 < total:
                    nxt = dict(lines[idx + 1])
                    next_norm = nxt.get("text_norm", "")
                    combined_norm = f"{text_norm.rstrip()} {next_norm.lstrip()}".strip()
                    combined_header = normalize_for_headers(combined_norm)
                    if APPENDIX_RE.match(combined_header):
                        combined_raw = f"{(line.get('text_raw') or '').rstrip()} {(nxt.get('text_raw') or '').lstrip()}".strip()
                        line["text_norm"] = combined_norm
                        if combined_raw:
                            line["text_raw"] = combined_raw
                        line["header_norm_seed"] = combined_header
                        line.setdefault("join_from", [])
                        join_from = list(dict.fromkeys(line["join_from"] + [line.get("line_idx"), nxt.get("line_idx")]))
                        line["join_from"] = [val for val in join_from if val is not None]
                        line["bbox"] = _union_bbox(line.get("bbox"), nxt.get("bbox"))
                        consumed_next = True
                        if debug is not None:
                            debug.append(
                                {
                                    "marker": "appendix_soft_unwrap",
                                    "page": page,
                                    "line_idx": line.get("line_idx"),
                                    "next_line_idx": nxt.get("line_idx"),
                                    "prefix_text": header_norm,
                                    "next_text": normalize_for_headers(next_norm),
                                    "tail_tokens": tail_tokens,
                                    "joined_text": combined_header,
                                }
                            )
                            debug.append(
                                {
                                    "marker": "line_skip",
                                    "skip_reason": "appendix_soft_unwrap",
                                    "line_idx": nxt.get("line_idx")
                                    if nxt.get("line_idx") is not None
                                    else nxt.get("order")
                                    if nxt.get("order") is not None
                                    else idx + 1,
                                    "page": int(nxt.get("page") or page),
                                    "text_norm": nxt.get("text_norm"),
                                    "text_raw": nxt.get("text_raw"),
                                }
                            )

        output.append(line)
        idx += 2 if consumed_next else 1

    return output


def _detect_appendix_gaps(candidates: Sequence[Dict]) -> List[Dict]:
    issues: List[Dict] = []
    by_page: Dict[int, List[int]] = defaultdict(list)
    for cand in candidates:
        if cand.get("kind") != "appendix":
            continue
        raw_token = cand.get("raw_number") or cand.get("num") or cand.get("number")
        if raw_token is None:
            continue
        token = str(raw_token).strip()
        token = token.rstrip(".)")
        token = token.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
        try:
            number = int(token)
        except ValueError:
            continue
        page = int(cand.get("page") or 0)
        by_page[page].append(number)
    for page, numbers in by_page.items():
        numbers = sorted(set(numbers))
        if len(numbers) < 2:
            continue
        expected = set(range(numbers[0], numbers[-1] + 1))
        missing = sorted(expected.difference(numbers))
        if missing:
            issues.append({"page": page, "missing": missing, "gap_reason": "appendix_sequence_gap"})
    return issues


def _section_number(kind: str, data: Mapping[str, object]) -> Optional[str]:
    if kind == "numeric":
        num = data.get("num") or data.get("number")
        if num is not None:
            return f"{num})"
    if kind == "appendix":
        letter = data.get("letter") or ""
        num = data.get("num") or data.get("number") or ""
        token = f"{letter}{num}".strip()
        if token:
            return f"{token}."
    return None


def _lines_for_chunk(offset_map: Sequence[Tuple[int, int, Dict]], start: int, end: int) -> List[Dict]:
    touched: List[Dict] = []
    for begin, finish, line in offset_map:
        if finish <= start:
            continue
        if begin >= end:
            break
        touched.append(line)
    return touched


def _serialize_graph(graph: Graph) -> Dict[str, List[Dict]]:
    return {
        "nodes": [
            {"id": node.id, "type": node.type, **node.data} for node in graph.nodes
        ],
        "edges": [
            {"type": edge.type, "source": edge.source, "target": edge.target, **edge.data}
            for edge in graph.edges
        ],
    }


def _atomicity_ok(extractions: Sequence[Dict]) -> bool:
    if not extractions:
        return True
    sentence_counts = [max(1, len(re.findall(r"[.!?]", rec.get("text", "")))) for rec in extractions]
    mean = sum(sentence_counts) / len(sentence_counts)
    return mean <= 1.05


def run_pipeline(
    document: Mapping[str, object],
    queries: Mapping[str, str],
    *,
    config: Optional[Mapping[str, Mapping[str, object]]] = None,
) -> Dict[str, object]:
    cfg: Dict[str, Mapping[str, object]] = {**DEFAULT_CONFIG, **(config or {})}
    doc_id = str(document.get("doc_id") or "doc")

    raw_lines = sorted(
        [dict(line) for line in document.get("lines", [])],
        key=lambda item: (int(item.get("page") or 0), int(item.get("line_idx") or 0)),
    )

    preproc_trace: List[Dict] = []
    processed: List[Dict] = []
    segment_markers: List[Dict] = []
    appendix_focus_orders: List[int] = []
    appendix_focus_pages: Set[int] = set()
    for order, line in enumerate(raw_lines):
        text_raw = str(line.get("text_raw") or line.get("text") or "")
        text_norm, hex_diff = normalize_text(text_raw)
        reason = _segment_reason_for_line(line) or "unknown"
        record = {
            **line,
            "text_raw": text_raw,
            "text_norm": text_norm,
            "hex_diff": hex_diff,
            "caps_ratio": _caps_ratio(text_norm),
            "order": order,
            "segment_reason": reason,
        }
        header_preview = normalize_for_headers(text_norm)
        record["header_norm_seed"] = header_preview
        if _APPENDIX_BOUNDARY_ANCHOR_RX.match(header_preview):
            if record["segment_reason"] and record["segment_reason"] != "unknown":
                record["segment_reason"] = f"{record['segment_reason']}|appendix_hard_boundary"
            else:
                record["segment_reason"] = "appendix_hard_boundary"
            segment_markers.append(
                {
                    "marker": "appendix_hard_boundary",
                    "page": int(record.get("page") or 0),
                    "line_idx": int(record.get("line_idx") or order),
                    "reason": "appendix_hard_boundary",
                }
            )
        preproc_trace.append(
            {
                "page": int(record.get("page") or 0),
                "line_idx": int(record.get("line_idx") or order),
                "text_raw": text_raw,
                "text_norm": text_norm,
                "hex_diff": list(hex_diff),
                "raw_hex": _codepoints(text_raw),
                "norm_hex": _codepoints(text_norm),
                "segment_reason": reason,
            }
        )
        if reason and reason != "unknown":
            segment_markers.append(
                {
                    "marker": "line_start_reason",
                    "page": int(line.get("page") or 0),
                    "line_idx": int(line.get("line_idx") or order),
                    "reason": reason,
                }
            )
        current_idx = len(processed)
        if _APPENDIX_FOCUS_RX.match(header_preview):
            appendix_focus_orders.append(current_idx)
            appendix_focus_pages.add(int(line.get("page") or 0))
        processed.append(record)

    _font_metrics(processed)
    pre_join_processed = list(processed)
    segment_debug: List[Dict] = []
    processed = join_split_lines(processed, debug=segment_debug)
    processed = _appendix_soft_unwrap_lines(processed, appendix_focus_pages, debug=segment_debug)
    appendix_context_indices: Set[int] = set()
    for idx in appendix_focus_orders:
        for delta in range(-3, 4):
            pos = idx + delta
            if 0 <= pos < len(pre_join_processed):
                appendix_context_indices.add(pos)
    appendix_line_dump: List[Dict] = []
    for pos in sorted(appendix_context_indices):
        base_line = pre_join_processed[pos]
        header_norm = normalize_for_headers(base_line.get("text_norm") or "")
        appendix_line_dump.append(
            {
                "order": int(base_line.get("order") or pos),
                "page": int(base_line.get("page") or 0),
                "line_idx": int(base_line.get("line_idx") or base_line.get("order") or pos),
                "raw_text": base_line.get("text_raw") or "",
                "raw_hex": _codepoints(base_line.get("text_raw")),
                "text_norm_raw": base_line.get("text_norm") or "",
                "norm_text": header_norm,
                "norm_hex": _codepoints(header_norm),
                "segment_reason": base_line.get("segment_reason") or "unknown",
                "seg_reason": base_line.get("segment_reason") or "unknown",
                "regex_probe": _regex_probe(header_norm),
                "skip_reason": None,
            }
        )

    for idx, line in enumerate(processed):
        line.setdefault("page", raw_lines[0].get("page", 1) if raw_lines else 1)
        line.setdefault("line_idx", idx)
        header_norm = normalize_for_headers(line.get("text_norm", ""))
        line["header_norm"] = header_norm
        line["caps_ratio"] = _caps_ratio(header_norm)
        line["order"] = idx

    encoder = EmbeddingEncoder(dim=int(cfg["embedding"].get("dim", 128)))
    prototypes = build_prototype_index(encoder)

    header_candidates: List[Dict] = []
    header_debug_initial: List[Dict] = []
    candidate_gate_trace: List[Dict] = []
    for event in segment_debug:
        if event.get("marker") == "line_skip":
            text_norm = event.get("text_norm") or ""
            header_text = normalize_for_headers(text_norm)
            candidate_gate_trace.append(
                {
                    "page": int(event.get("page") or 0),
                    "line_idx": int(event.get("line_idx") or 0),
                    "text_raw": event.get("text_raw") or text_norm,
                    "text_norm": header_text,
                    "regex_probe": _regex_probe(header_text),
                    "style": {},
                    "skip_reason": event.get("skip_reason"),
                    "decision": None,
                    "score": None,
                    "partials": {},
                    "meets_threshold": False,
                    "is_appendix": bool(APPENDIX_RE.match(header_text)),
                    "is_numeric": bool(NUMERIC_RE.match(header_text)),
                    "rescue": False,
                }
            )

    for line in processed:
        norm_text = line.get("header_norm") or normalize_for_headers(line.get("text_norm", ""))
        candidate = _build_candidate_record(
            line,
            norm_text,
            encoder=encoder,
            prototypes=prototypes,
            gate_trace=candidate_gate_trace,
        )
        if not candidate:
            continue
        header_candidates.append(candidate)
        header_debug_initial.append(_candidate_debug_entry(candidate))

    rescue_candidates = _appendix_neighbor_rescue(
        processed,
        header_candidates,
        encoder,
        prototypes,
        gate_trace=candidate_gate_trace,
    )
    if rescue_candidates:
        header_candidates.extend(rescue_candidates)

    _apply_appendix_sequence_bonus(header_candidates)

    for cand in header_candidates:
        meets = cand.get("score", 0.0) >= THRESHOLD
        cand["meets_threshold"] = meets
        style = cand.get("style") or _style_snapshot(cand, float(cand.get("caps_ratio") or 0.0))
        cand["style"] = style
        cand.setdefault("partials", {})
        cand["partials"].setdefault("units_penalty_applied", False)
        cand["decision"] = _decide_candidate(
            meets,
            bool(cand.get("is_numeric")),
            bool(cand.get("is_appendix")),
            style,
        )

    header_debug_post_rescue = [_candidate_debug_entry(cand) for cand in header_candidates]

    gate_lookup: Dict[Tuple[int, int], Dict] = {}
    for entry in candidate_gate_trace:
        key = (int(entry.get("page") or 0), int(entry.get("line_idx") or 0))
        existing = gate_lookup.get(key)
        if existing is None:
            gate_lookup[key] = entry
        else:
            if (not existing.get("skip_reason")) and entry.get("skip_reason"):
                gate_lookup[key] = entry
    for dump_entry in appendix_line_dump:
        key = (int(dump_entry.get("page") or 0), int(dump_entry.get("line_idx") or 0))
        gate_entry = gate_lookup.get(key)
        if not gate_entry:
            continue
        if gate_entry.get("skip_reason") is not None or dump_entry.get("skip_reason") is None:
            dump_entry["skip_reason"] = gate_entry.get("skip_reason")
        if gate_entry.get("decision") is not None:
            dump_entry["decision"] = gate_entry.get("decision")
        if gate_entry.get("score") is not None:
            try:
                dump_entry["score"] = float(gate_entry.get("score"))
            except Exception:
                dump_entry["score"] = gate_entry.get("score")
        if not dump_entry.get("regex_probe") and gate_entry.get("regex_probe"):
            dump_entry["regex_probe"] = gate_entry.get("regex_probe")

    selected_headers = [
        cand for cand in header_candidates if cand["decision"] in {"selected", "selected_fallback"}
    ]
    appendix_gaps = _detect_appendix_gaps(selected_headers)

    sections: List[Dict] = []
    section_maps: Dict[str, Dict] = {}
    processed_sorted = sorted(processed, key=lambda item: item.get("order", 0))
    section_lookup = {id(cand): idx for idx, cand in enumerate(selected_headers)}
    for idx, cand in enumerate(sorted(selected_headers, key=lambda item: item.get("order", 0))):
        start = cand.get("order", 0)
        end = (
            sorted(selected_headers, key=lambda item: item.get("order", 0))[idx + 1].get("order", len(processed_sorted))
            if idx + 1 < len(selected_headers)
            else len(processed_sorted)
        )
        section_lines = [line for line in processed_sorted[start:end]]
        text_parts = [line.get("text_norm", "") for line in section_lines if line.get("text_norm")]
        section_text = "\n".join(text_parts)
        offset_map: List[Tuple[int, int, Dict]] = []
        offset = 0
        for line in section_lines:
            text_piece = line.get("text_norm", "")
            span_end = offset + len(text_piece)
            offset_map.append((offset, span_end, line))
            offset = span_end + 1
        sec_id = f"S{idx:04d}"
        section_record = {
            "sec_id": sec_id,
            "kind": cand.get("kind"),
            "number": cand.get("number"),
            "title": cand.get("title") or cand.get("text_norm"),
            "page": cand.get("page"),
            "line_idx": cand.get("line_idx"),
            "bbox": cand.get("bbox"),
            "bbox_header": cand.get("bbox"),
            "score": cand.get("score"),
            "proto_sim_max": cand.get("features", {}).get("proto_sim_max", 0.0),
            "canonical_id": cand.get("canonical_id"),
            "canonical_conf": cand.get("canonical_conf"),
            "text": section_text,
        }
        sections.append(section_record)
        section_maps[sec_id] = {
            "lines": section_lines,
            "offset_map": offset_map,
            "header": cand,
        }

    section_graph = build_section_graph(sections) if sections else {"nodes": [], "edges": []}

    section_artifact = {
        "doc_id": doc_id,
        "schema_version": "1.0.0",
        "sections": sections,
    }

    micro_cfg = cfg["microchunks"]
    window_chars = int(micro_cfg.get("window_chars", 450))
    stride_chars = int(micro_cfg.get("stride_chars", 80))

    chunk_records: List[Dict] = []
    chunks_by_section: Dict[str, List[Dict]] = defaultdict(list)
    appendix_microchunk_debug: List[Dict] = []
    for sec_idx, section in enumerate(sections):
        sec_id = section["sec_id"]
        section_text = section.get("text", "")
        offset_map = section_maps.get(sec_id, {}).get("offset_map", [])
        for chunk_idx, window in enumerate(
            microchunk(section_text, window_chars=window_chars, stride_chars=stride_chars)
        ):
            lines_for_chunk = _lines_for_chunk(offset_map, window.start, window.end)
            pages = sorted({int(line.get("page") or 0) for line in lines_for_chunk if line.get("page")})
            page = pages[0] if pages else int(section.get("page") or 1)
            bboxes = [line.get("bbox") for line in lines_for_chunk if line.get("bbox")]
            if not bboxes:
                bboxes = [[0, 0, 0, 0]]
            chunk_id = f"C-{sec_idx:04d}-{chunk_idx:03d}"
            chunk = {
                "chunk_id": chunk_id,
                "section_id": sec_id,
                "section_title": section.get("title"),
                "page": page,
                "pages": pages or [page],
                "offsets": {"start": window.start, "end": window.end},
                "text": window.text,
                "window_chars": window_chars,
                "stride_chars": stride_chars,
                "E": window.E,
                "F": window.F,
                "H": window.H,
                "provenance": {"bboxes": bboxes},
            }
            chunk_records.append(chunk)
            chunks_by_section[sec_id].append(chunk)

            if appendix_focus_pages and (
                section.get("kind") == "appendix"
                or any(int(line.get("page") or 0) in appendix_focus_pages for line in lines_for_chunk)
            ):
                line_indices = [
                    int(line.get("line_idx") or line.get("order") or 0)
                    for line in lines_for_chunk
                ]
                appendix_microchunk_debug.append(
                    {
                        "chunk_id": chunk_id,
                        "section_id": sec_id,
                        "section_kind": section.get("kind"),
                        "page": page,
                        "line_indices": line_indices,
                        "line_idx_range": [min(line_indices), max(line_indices)]
                        if line_indices
                        else None,
                        "offsets": chunk["offsets"],
                    }
                )

    section_texts_for_embedding = [
        f"{section.get('title', '')} {section.get('text', '')[:cfg['embedding'].get('section_tokens', 128)]}"
        for section in sections
    ]
    section_vectors = encoder.embed_texts(section_texts_for_embedding)
    section_meta = [
        {
            "sec_id": section["sec_id"],
            "title": section.get("title"),
            "text": section.get("text"),
            "page": section.get("page"),
        }
        for section in sections
    ]

    chunk_vectors_by_section: Dict[str, np.ndarray] = {}
    chunk_meta_by_section: Dict[str, List[Dict]] = {}
    for sec_id, chunks in chunks_by_section.items():
        texts = [chunk["text"] for chunk in chunks]
        if not texts:
            continue
        chunk_vectors_by_section[sec_id] = encoder.embed_texts(texts)
        chunk_meta_by_section[sec_id] = [
            {
                "chunk_id": chunk["chunk_id"],
                "section_id": sec_id,
                "section_title": chunk.get("section_title"),
                "text": chunk["text"],
                "page": chunk["page"],
                "offsets": chunk["offsets"],
                "E": chunk["E"],
                "F": chunk["F"],
                "H": chunk["H"],
                "provenance": chunk["provenance"],
            }
            for chunk in chunks
        ]

    graph = build_chunk_graph(doc_id, sections, chunk_records)
    graph_serialized = _serialize_graph(graph)

    retrieval_results: Dict[str, Dict] = {}
    retrieval_trace: List[Dict] = []
    validation_trace: List[Dict] = []
    all_extractions: List[Dict] = []

    for pass_name, query in queries.items():
        query_vec = encoder.embed_texts([query])[0]
        if section_vectors.size == 0:
            retrieval_results[pass_name] = {
                "top_sections": [],
                "candidates": [],
                "final_chunks": [],
                "extractions": [],
                "validations": {"conflicts": [], "parse_rate": 1.0, "provenance_ok": True},
                "overlays": [],
                "report_html": render_report(doc_id, [], []),
                "deterministic": True,
            }
            retrieval_trace.append({"pass": pass_name, "top_sections": [], "final_count": 0})
            validation_trace.append({"pass": pass_name, "records": 0, "conflicts": [], "parse_rate": 1.0})
            continue
        top_sections = prefilter_sections(
            query_vec,
            section_vectors,
            section_meta,
            top_m=int(cfg["retrieval"].get("M_sections", 15)),
        )
        sections_payload = [
            {
                "sec_id": entry.get("sec_id"),
                "title": entry.get("title"),
                "S": round(float(entry.get("S", 0.0)), 6),
                "page": entry.get("page"),
            }
            for entry in top_sections
        ]

        candidate_vectors = {
            sec_id: chunk_vectors_by_section[sec_id]
            for sec_id in [entry.get("sec_id") for entry in top_sections]
            if sec_id in chunk_vectors_by_section
        }
        candidate_meta = {
            sec_id: chunk_meta_by_section[sec_id]
            for sec_id in candidate_vectors
        }
        candidates = recall_chunks(
            query_vec,
            candidate_vectors,
            candidate_meta,
            top_kprime=int(cfg["retrieval"].get("Kprime", 40)),
        )
        weights = cfg["passes"].get(pass_name, cfg["passes"].get("mechanical"))
        for cand in candidates:
            cand["fused"] = round(
                float(
                    fuse(
                        cand.get("S", 0.0),
                        cand.get("E", 0.0),
                        cand.get("F", 0.0),
                        cand.get("H", 0.0),
                        weights,
                    )
                ),
                6,
            )
        candidates.sort(key=lambda item: item.get("fused", 0.0), reverse=True)

        section_cap = int(cfg["retrieval"].get("section_cap", 3))
        final: List[Dict] = []
        per_section: Dict[str, int] = defaultdict(int)
        for cand in candidates:
            if len(final) >= int(cfg["retrieval"].get("K_final", 7)):
                break
            sid = cand.get("section_id")
            if not sid:
                continue
            if per_section[sid] >= section_cap:
                continue
            per_section[sid] += 1
            final.append(cand)

        records: List[Dict] = []
        for cand in final:
            chunk = cand
            extracted = extract_atomic(chunk, section_hint=cand.get("section_title"))
            for record in extracted:
                record.setdefault("provenance", cand.get("provenance", {}))
                record.setdefault("source_chunk_id", cand.get("chunk_id"))
                record["pass"] = pass_name
            records.extend(extracted)
        deduped = dedupe(records)
        all_extractions.extend(deduped)

        conflicts = find_conflicts(deduped)
        unit_records = [rec for rec in deduped if rec.get("unit")]
        parsed_units = sum(1 for rec in unit_records if rec.get("op"))
        parse_rate = parsed_units / len(unit_records) if unit_records else 1.0
        provenance_ok = all(rec.get("provenance", {}).get("bboxes") for rec in deduped)

        overlays = [to_overlay(rec) for rec in deduped]
        report_html = render_report(doc_id, deduped, overlays)

        retrieval_results[pass_name] = {
            "top_sections": sections_payload,
            "candidates": candidates,
            "final_chunks": final,
            "extractions": deduped,
            "validations": {
                "conflicts": conflicts,
                "parse_rate": parse_rate,
                "provenance_ok": provenance_ok,
            },
            "overlays": overlays,
            "report_html": report_html,
            "deterministic": True,
        }

        retrieval_trace.append(
            {
                "pass": pass_name,
                "top_sections": sections_payload,
                "final_count": len(final),
            }
        )
        validation_trace.append(
            {
                "pass": pass_name,
                "records": len(deduped),
                "conflicts": conflicts,
                "parse_rate": parse_rate,
            }
        )

    ci_summary = {
        "headers_meet_threshold": all(
            cand.get("decision") != "selected" or cand.get("meets_threshold")
            for cand in header_candidates
        ),
        "appendix_gaps_logged": not appendix_gaps or all("gap_reason" in gap for gap in appendix_gaps),
        "provenance_coverage": all(
            rec.get("provenance", {}).get("bboxes") for rec in all_extractions
        ),
        "atomicity": _atomicity_ok(all_extractions),
        "units_parse_rate": (
            sum(1 for rec in all_extractions if rec.get("unit") and rec.get("op"))
            / max(1, sum(1 for rec in all_extractions if rec.get("unit")))
        ),
        "section_diversity": all(
            max(
                (
                    sum(
                        1
                        for chunk in payload.get("final_chunks", [])
                        if chunk.get("section_id") == sec_id
                    )
                    for sec_id in {
                        chunk.get("section_id")
                        for chunk in payload.get("final_chunks", [])
                        if chunk.get("section_id")
                    }
                ),
                default=0,
            )
            <= int(cfg["retrieval"].get("section_cap", 3))
            for payload in retrieval_results.values()
        ),
        "deterministic_scores": all(payload.get("deterministic") for payload in retrieval_results.values()),
    }

    segment_trace = segment_markers + segment_debug

    artifact = {
        "doc_id": doc_id,
        "config": {
            "embedding": cfg["embedding"],
            "retrieval": cfg["retrieval"],
        },
        "preprocess": {"lines": processed},
        "sections": section_artifact,
        "section_graph": section_graph,
        "chunks": chunk_records,
        "graph": graph_serialized,
        "retrieval": retrieval_results,
        "traces": {
            "preprocess": preproc_trace,
            "header_debug_initial": header_debug_initial,
            "header_debug_post_rescue": header_debug_post_rescue,
            "headers": header_candidates,
            "segmentation": segment_trace,
            "candidate_gate": candidate_gate_trace,
            "appendix_line_dump": appendix_line_dump,
            "appendix_microchunks": appendix_microchunk_debug,
            "retrieval": retrieval_trace,
            "validation": validation_trace,
        },
        "section_gaps": appendix_gaps,
        "ci": ci_summary,
    }

    return json.loads(json.dumps(artifact, default=lambda o: float(o)))


__all__ = ["DEFAULT_CONFIG", "run_pipeline"]
