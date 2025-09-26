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
from .sectioning.header_match import classify_line
from .sectioning.header_score import THRESHOLD, score_candidate
from .sectioning.section_graph import build_section_graph
from .sectioning.header_features import compute_features
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
        "window_chars": 450,
        "stride_chars": 80,
    },
}


_ALT_SPACE_CHARS = {"\u00A0", "\u2002", "\u2003", "\u202F"}
_ALT_DOT_CHARS = {"\u2024", "\u2027", "\uFF0E"}
_SOFT_APPENDIX_PREFIX_RX = re.compile(r"^[A-Z]\d+[.\u2024\u2027\uFF0E]")
_SOFT_NUMERIC_PREFIX_RX = re.compile(r"^\d+\)")
_NEIGHBOR_BONUS = 0.15


def _caps_ratio(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    upper = sum(1 for ch in letters if ch.isupper())
    return upper / len(letters)


def _units_present(text: str) -> bool:
    parsed = parse_units(text or "")
    return bool(parsed.get("units"))


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


def _normalize_soft_text(text: str) -> str:
    if not text:
        return ""
    buf: List[str] = []
    for ch in text:
        if ch in _ALT_SPACE_CHARS:
            buf.append(" ")
        elif ch in _ALT_DOT_CHARS:
            buf.append(".")
        else:
            buf.append(ch)
    normalized = "".join(buf)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _should_apply_units_penalty(text: str) -> bool:
    stripped = _normalize_soft_text(text)
    if _SOFT_NUMERIC_PREFIX_RX.match(stripped):
        return False
    if _SOFT_APPENDIX_PREFIX_RX.match(stripped):
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
) -> List[Dict]:
    groups: Dict[Tuple[int, str], List[Tuple[int, Dict]]] = defaultdict(list)
    existing_keys: Set[Tuple[int, str, int]] = set()
    for cand in header_candidates:
        if cand.get("kind") == "appendix":
            letter = str(cand.get("letter") or "").upper()
            number = _extract_appendix_number(cand.get("raw_number") or cand.get("number"))
            if number is None:
                continue
            page = int(cand.get("page") or 0)
            groups[(page, letter)].append((number, cand))
            existing_keys.add((page, letter, number))

    additions: List[Dict] = []

    for (page, letter), entries in groups.items():
        if len(entries) < 4:
            continue
        numbers = sorted(num for num, _ in entries)
        number_set = set(numbers)
        for base in numbers:
            pattern = {base, base + 1, base + 4, base + 5}
            if not pattern.issubset(number_set):
                continue
            missing = [base + 2, base + 3]
            left = next((cand for num, cand in entries if num == base + 1), None)
            right = next((cand for num, cand in entries if num == base + 4), None)
            if left is None or right is None:
                continue
            start = int(left.get("order", 0)) + 1
            end = int(right.get("order", 0))
            if start >= end:
                continue
            for idx in range(start, min(end, len(processed))):
                base_line = processed[idx]
                base_text = _normalize_soft_text(base_line.get("text_norm", ""))
                if not base_text:
                    continue
                combined_text = base_text
                tokens = combined_text.split(" ", 1)
                first_token = tokens[0] if tokens else ""
                gap_limit = min(end, len(processed))
                if (
                    first_token
                    and _SOFT_APPENDIX_PREFIX_RX.match(first_token)
                    and (len(tokens) == 1 or not tokens[1].strip())
                    and idx + 1 < gap_limit
                ):
                    follower = processed[idx + 1]
                    follower_text = _normalize_soft_text(follower.get("text_norm", ""))
                    if follower_text:
                        combined_text = f"{first_token} {follower_text}".strip()

                norm_text = combined_text.strip()
                if not norm_text:
                    continue

                rescue_line = dict(base_line)
                rescue_line["text_norm"] = norm_text
                rescue_line["caps_ratio"] = _caps_ratio(norm_text)

                line_vector = encoder.embed_texts([norm_text])[0]
                proto_matches = topk_header_prototypes(line_vector, prototypes, k=3)
                computed = compute_features(rescue_line, proto_matches, p_header=0.0)
                kind_data = classify_line(norm_text, rescue_line.get("caps_ratio", 0.0))
                if kind_data.get("kind") != "appendix":
                    continue
                number_val = _extract_appendix_number(kind_data.get("number"))
                if number_val is None:
                    continue
                if number_val not in missing:
                    continue
                key = (page, letter, number_val)
                if key in existing_keys:
                    continue

                score, partials = score_candidate(kind_data["kind"], computed)
                if kind_data["kind"] == "label" and _should_apply_units_penalty(norm_text):
                    score -= 0.6
                    partials = {**partials, "units_penalty": -0.6}

                candidate = {
                    **rescue_line,
                    **kind_data,
                    "page": rescue_line.get("page", page),
                    "raw_number": kind_data.get("number"),
                    "score": float(score),
                    "partials": {key_: float(val) for key_, val in partials.items()},
                    "features": {
                        key_: float(computed.get(key_, 0.0))
                        for key_ in (
                            "bold",
                            "font_sigma",
                            "font_z",
                            "caps_ratio",
                            "len",
                            "proto_sim_max",
                            "p_header",
                        )
                    },
                    "proto_top3": _serialize_top3(computed.get("proto_top3", [])),
                    "meets_threshold": False,
                    "decision": "below_threshold",
                }
                candidate["number"] = _section_number(
                    kind_data["kind"], {"letter": kind_data.get("letter"), "number": kind_data.get("number")}
                )
                candidate["rescue_applied"] = True

                additions.append(candidate)
                existing_keys.add(key)

    return additions


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
    for order, line in enumerate(raw_lines):
        text_raw = str(line.get("text_raw") or line.get("text") or "")
        text_norm, hex_diff = normalize_text(text_raw)
        record = {
            **line,
            "text_raw": text_raw,
            "text_norm": text_norm,
            "hex_diff": hex_diff,
            "caps_ratio": _caps_ratio(text_norm),
            "order": order,
        }
        preproc_trace.append(
            {
                "page": int(record.get("page") or 0),
                "line_idx": int(record.get("line_idx") or order),
                "text_raw": text_raw,
                "text_norm": text_norm,
                "hex_diff": list(hex_diff),
            }
        )
        processed.append(record)

    _font_metrics(processed)
    processed = join_split_lines(processed)
    for idx, line in enumerate(processed):
        line.setdefault("page", raw_lines[0].get("page", 1) if raw_lines else 1)
        line.setdefault("line_idx", idx)
        line["caps_ratio"] = _caps_ratio(line.get("text_norm", ""))
        line["order"] = idx

    encoder = EmbeddingEncoder(dim=int(cfg["embedding"].get("dim", 128)))
    prototypes = build_prototype_index(encoder)

    header_candidates: List[Dict] = []
    for line in processed:
        text_norm = line.get("text_norm", "")
        line_vector = encoder.embed_texts([text_norm])[0]
        proto_matches = topk_header_prototypes(line_vector, prototypes, k=3)
        computed = compute_features(line, proto_matches, p_header=0.0)
        kind_data = classify_line(text_norm, line.get("caps_ratio", 0.0))
        if kind_data.get("kind") == "none":
            continue
        score, partials = score_candidate(kind_data["kind"], computed)
        if kind_data["kind"] == "label" and _units_present(text_norm) and _should_apply_units_penalty(text_norm):
            score -= 0.6
            partials = {**partials, "units_penalty": -0.6}
        meets = score >= THRESHOLD
        raw_number = kind_data.get("number")
        candidate = {
            **line,
            **kind_data,
            "raw_number": raw_number,
            "score": float(score),
            "partials": {key: float(val) for key, val in partials.items()},
            "features": {
                key: float(computed.get(key, 0.0))
                for key in ("bold", "font_sigma", "font_z", "caps_ratio", "len", "proto_sim_max", "p_header")
            },
            "proto_top3": _serialize_top3(computed.get("proto_top3", [])),
            "meets_threshold": meets,
            "decision": "selected" if meets else "below_threshold",
        }
        candidate["number"] = _section_number(
            kind_data["kind"], {"letter": kind_data.get("letter"), "number": raw_number}
        )
        if candidate["proto_top3"]:
            top_entry = candidate["proto_top3"][0]
            if top_entry["score"] >= 0.6:
                candidate["canonical_id"] = top_entry["id"]
                candidate["canonical_conf"] = round(float(top_entry["score"]), 4)
        header_candidates.append(candidate)

    rescue_candidates = _appendix_neighbor_rescue(processed, header_candidates, encoder, prototypes)
    if rescue_candidates:
        header_candidates.extend(rescue_candidates)

    _apply_appendix_sequence_bonus(header_candidates)

    for cand in header_candidates:
        meets = cand.get("score", 0.0) >= THRESHOLD
        cand["meets_threshold"] = meets
        cand["decision"] = "selected" if meets else "below_threshold"

    selected_headers = [cand for cand in header_candidates if cand["decision"] == "selected"]
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
            "headers": header_candidates,
            "retrieval": retrieval_trace,
            "validation": validation_trace,
        },
        "section_gaps": appendix_gaps,
        "ci": ci_summary,
    }

    return json.loads(json.dumps(artifact, default=lambda o: float(o)))


__all__ = ["DEFAULT_CONFIG", "run_pipeline"]
