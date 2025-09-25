# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional, Iterable
import re
import os
import csv
import json
import copy

try:
    from rapidfuzz.fuzz import ratio as fuzz_ratio
except Exception:
    import difflib
    def fuzz_ratio(a, b): return int(100 * difflib.SequenceMatcher(None, a or "", b or "").ratio())

from .header_detector import (
    score_header_candidate,
    score_header_candidate_debug,
    HEADER_RX,
    ALT_HEADER_RX,
    ALLCAPS_HEADER_RX,
)
from .header_levels import map_font_sizes_to_levels, infer_heading_level
from . import header_config
from .line_normalize import normalize_page_lines
from .layout_segmenter import apply_prefilter
from .patterns_rfq import RFQ_SECTION_RES

APPENDIX_ALNUM_RX = re.compile(r'^\s*[A-Za-z]\d+\.\s+')
APPENDIX_WORD_RX = re.compile(r'^\s*(Appendix|Annex)\s+[A-Za-z]', re.IGNORECASE)

_PRE_REGEX_PATTERNS = [
    ("HEADER_RX", HEADER_RX),
    ("ALT_HEADER_RX", ALT_HEADER_RX),
    ("ALLCAPS_HEADER_RX", ALLCAPS_HEADER_RX),
]
_PRE_REGEX_PATTERNS.extend((f"RFQ_{idx}", rx) for idx, rx in enumerate(RFQ_SECTION_RES))


def select_candidates(
    page_lines: List[str],
    page_styles: List[dict],
    *,
    doc_id: Optional[str] = None,
    page_idx: int = 0,
) -> Tuple[List[dict], List[Dict[str, Any]]]:
    doc_component = header_config.sanitize_component(doc_id or "document")
    normalized_rows = normalize_page_lines(doc_component, page_idx, page_lines, page_styles)
    filtered_rows, _ledger = apply_prefilter(doc_component, page_idx, normalized_rows)
    _write_precandidate_dump(doc_component, page_idx, normalized_rows)

    font_sizes = [
        (row.get("style") or {}).get("font_size")
        for row in normalized_rows
        if (row.get("style") or {}).get("font_size") is not None
    ]
    size_map = (
        map_font_sizes_to_levels(font_sizes, max_levels=4)
        if header_config.CONFIG.get("use_font_clusters", True)
        else {}
    )

    candidates: List[dict] = []
    for row in filtered_rows:
        text_norm = (row.get("text_norm") or "").strip()
        if not text_norm:
            continue

        style = row.get("style") or {}
        score = score_header_candidate(text_norm, style)
        if score < header_config.CONFIG.get("ambiguous_score_threshold", 1.10):
            row["candidate_considered"] = False
            continue

        caps = float(style.get("caps_ratio") or 0.0)
        if caps >= 0.75:
            score += 0.25

        match = header_config.SECTION_PREFIX_RX.search(text_norm)
        section_number = (match.group(1) if match else "").strip()
        level = infer_heading_level(style.get("font_size"), section_number, size_map)

        candidate = {
            "line_idx": row.get("line_idx"),
            "text": row.get("text_trim") or text_norm,
            "text_norm": text_norm,
            "style": {
                "font_sigma_rank": style.get("font_sigma_rank"),
                "bold": style.get("bold"),
                "caps_ratio": style.get("caps_ratio"),
                "font_size": style.get("font_size"),
            },
            "score": score,
            "section_number": section_number,
            "level": level,
        }
        row["candidate_considered"] = True
        row["candidate_section_number"] = section_number
        row["candidate_level"] = level
        row["candidate_score"] = score
        candidates.append(candidate)

    candidates.sort(key=lambda x: (-x["score"], x["line_idx"]))
    deduped: List[dict] = []
    seen_text: List[str] = []
    for cand in candidates:
        key_text = cand.get("text_norm") or cand.get("text") or ""
        if seen_text and fuzz_ratio(seen_text[-1], key_text) >= header_config.CONFIG.get(
            "dedup_fuzzy_threshold", 90
        ):
            continue
        seen_text.append(key_text)
        deduped.append(cand)

    max_candidates = header_config.CONFIG.get("max_candidates_per_page", 40)
    limited = deduped[: max_candidates]

    accepted_indices = {cand.get("line_idx") for cand in limited}
    for row in normalized_rows:
        row["candidate_retained"] = row.get("line_idx") in accepted_indices

    return limited, normalized_rows


def _match_pre_regex(text: str) -> List[str]:
    hits: List[str] = []
    if not text:
        return hits
    for label, rx in _PRE_REGEX_PATTERNS:
        try:
            if rx and rx.search(text):
                hits.append(label)
        except Exception:
            continue
    return hits


def _write_precandidate_dump(doc_id: str, page_idx: int, rows: List[Dict[str, Any]]) -> None:
    for row in rows:
        text_norm = row.get("text_norm") or ""
        hits = _match_pre_regex(text_norm)
        row["pre_regex_hits"] = hits
        row["appendix_regex_hit"] = bool(
            APPENDIX_ALNUM_RX.match(text_norm) or APPENDIX_WORD_RX.match(text_norm)
        )
        match = header_config.SECTION_PREFIX_RX.search(text_norm)
        row["section_prefix_guess"] = (match.group(1) if match else "").strip()

    if not header_config.DEBUG_HEADERS:
        return

    base_dir = header_config.CONFIG.get("debug_dir") or header_config.DEBUG_DIR or "./_debug/headers"
    page_dir = os.path.join(base_dir, doc_id, f"page_{page_idx:04d}")
    header_config._ensure_dir(page_dir)
    precand_path = os.path.join(page_dir, "precandidates.csv")
    with open(precand_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "line_idx",
                "text_norm",
                "pre_regex_hits",
                "appendix_regex_hit",
                "section_prefix_guess",
                "x_left",
                "font_size",
                "bold",
                "caps_ratio",
            ]
        )
        for row in rows:
            style = row.get("style") or {}
            writer.writerow(
                [
                    row.get("line_idx"),
                    row.get("text_norm"),
                    "|".join(row.get("pre_regex_hits") or []),
                    bool(row.get("appendix_regex_hit")),
                    row.get("section_prefix_guess"),
                    style.get("x_left"),
                    style.get("font_size"),
                    style.get("bold"),
                    style.get("caps_ratio"),
                ]
            )


def _unpack_page_debug_entry(entry: Any) -> Tuple[int, List[dict], str, List[Dict[str, Any]]]:
    if isinstance(entry, dict):
        page_idx = int(entry.get("page_idx") or entry.get("page") or 0)
        return (
            page_idx,
            list(entry.get("candidates") or []),
            entry.get("page_text") or entry.get("text") or "",
            list(entry.get("line_records") or entry.get("lines") or []),
        )
    if isinstance(entry, (list, tuple)):
        if len(entry) >= 4:
            return int(entry[0]), list(entry[1] or []), entry[2] or "", list(entry[3] or [])
        if len(entry) >= 3:
            return int(entry[0]), list(entry[1] or []), entry[2] or "", []
    return 0, [], "", []


def build_adjudication_prompt(page_text: str, candidates: List[dict], context_chars: int) -> str:
    # Single-page prompt
    def window_around_line(text: str, target: str, chars: int = 600) -> str:
        pos = text.find(target[:120])
        if pos < 0:
            return text[:chars]
        start = max(0, pos - chars // 2)
        end = min(len(text), pos + len(target) + chars // 2)
        return text[start:end]

    blob = "\n".join(page_text.splitlines())
    lines = [f"- [{c['line_idx']}]: {c['text']}" for c in candidates]
    ctxs = [
        f"[{c['line_idx']}]: {window_around_line(blob, c['text'], chars=context_chars)}"
        for c in candidates
    ]

    prefix = (
        "You are validating section headings in an engineering RFQ/spec. "
        "Return ONLY JSON list: [{\"section_number\":\"\",\"section_name\":\"\",\"line_idx\":0}]. No prose.\n\n"
        "CANDIDATE_LINES:\n"
    )
    return (
        prefix
        + "\n".join(lines)
        + "\n\nPAGE_TEXT_SNIPPETS:\n"
        + "\n".join(ctxs)
    )


def _dump_page_debug(
    doc_id: str,
    page_idx: int,
    page_text: str,
    candidates: List[dict],
    line_records: Optional[List[Dict[str, Any]]] = None,
    llm_prompt: Optional[str] = None,
    llm_json: Optional[List[Dict[str, Any]]] = None,
) -> None:
    if not header_config.CONFIG.get("debug"):
        return

    base_dir = header_config.CONFIG.get("debug_dir") or header_config.DEBUG_DIR or "./_debug/headers"
    doc_component = header_config.sanitize_component(doc_id or "document")
    page_dir = os.path.join(base_dir, doc_component, f"page_{page_idx:04d}")
    header_config._ensure_dir(page_dir)

    threshold = header_config.ACCEPT_SCORE_THRESHOLD
    csv_path = os.path.join(page_dir, "candidates_scored.csv")
    scored_entries: List[Dict[str, Any]] = []
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "line_idx",
                "text_norm",
                "regex_hits",
                "numbering_depth",
                "font_size",
                "bold",
                "caps",
                "disqualifiers",
                "partial_scores_json",
                "total_score",
                "threshold",
                "accepted",
            ]
        )
        for cand in candidates:
            text_norm = cand.get("text_norm") or (cand.get("text") or "")
            breakdown = score_header_candidate_debug(text_norm, style=cand.get("style") or {})
            accepted = breakdown.total >= threshold
            cand["_score_total"] = breakdown.total
            cand["_score_accepted"] = accepted
            writer.writerow(
                [
                    cand.get("line_idx"),
                    breakdown.text,
                    "|".join(breakdown.regex_hits),
                    breakdown.numbering_depth,
                    breakdown.font_size,
                    breakdown.bold,
                    breakdown.caps,
                    "|".join(breakdown.disqualifiers),
                    json.dumps(breakdown.partial_scores, ensure_ascii=False),
                    f"{breakdown.total:.2f}",
                    f"{threshold:.2f}",
                    accepted,
                ]
            )
            scored_entries.append(
                {
                    "line_idx": cand.get("line_idx"),
                    "text": breakdown.text,
                    "regex_hits": breakdown.regex_hits,
                    "numbering_depth": breakdown.numbering_depth,
                    "font_size": breakdown.font_size,
                    "bold": breakdown.bold,
                    "caps": breakdown.caps,
                    "disqualifiers": breakdown.disqualifiers,
                    "partial_scores": breakdown.partial_scores,
                    "total_score": breakdown.total,
                    "threshold": threshold,
                    "accepted": accepted,
                }
            )
            if line_records:
                for row in line_records:
                    if row.get("line_idx") == cand.get("line_idx"):
                        row["candidate_score_total"] = breakdown.total
                        row["candidate_score_detail"] = breakdown.partial_scores
                        row["candidate_score_regex_hits"] = breakdown.regex_hits
                        row["candidate_score_accepted"] = accepted
                        break

    llm_indices = set()
    if llm_json:
        for item in llm_json:
            try:
                idx = int(item.get("line_idx"))
            except Exception:
                continue
            llm_indices.add(idx)

    for entry in scored_entries:
        entry["llm_selected"] = bool(llm_indices and entry["line_idx"] in llm_indices)

    analysis_path = os.path.join(page_dir, "analysis.json")
    with open(analysis_path, "w", encoding="utf-8") as fh:
        json.dump(
            sorted(scored_entries, key=lambda item: item.get("total_score", 0.0), reverse=True),
            fh,
            ensure_ascii=False,
            indent=2,
        )

    with open(os.path.join(page_dir, "candidates.json"), "w", encoding="utf-8") as fh:
        json.dump(candidates, fh, ensure_ascii=False, indent=2)

    with open(os.path.join(page_dir, "page.txt"), "w", encoding="utf-8") as fh:
        fh.write(page_text)

    if llm_prompt is not None:
        with open(os.path.join(page_dir, "llm_prompt.txt"), "w", encoding="utf-8") as fh:
            fh.write(llm_prompt)

    if llm_json is not None:
        with open(os.path.join(page_dir, "llm_selection.json"), "w", encoding="utf-8") as fh:
            json.dump(llm_json, fh, ensure_ascii=False, indent=2)


def write_page_debug(
    doc_id: str,
    page_idx: int,
    page_text: str,
    candidates: List[dict],
    line_records: Optional[List[Dict[str, Any]]] = None,
    *,
    llm_prompt: Optional[str] = None,
    llm_json: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Persist debug artefacts for a header page snapshot if debug mode is enabled."""

    _dump_page_debug(
        doc_id,
        page_idx,
        page_text,
        candidates,
        line_records,
        llm_prompt=llm_prompt,
        llm_json=llm_json,
    )


def dump_appendix_audit(
    doc_id: str,
    pages_debug: List[Any],
) -> None:
    if not header_config.CONFIG.get("debug"):
        return

    rx = re.compile(r"^\s*(?:Appendix\s+[A-Za-z]|[A-Za-z]\d+\.)")
    base_dir = header_config.CONFIG.get("debug_dir") or header_config.DEBUG_DIR or "./_debug/headers"
    doc_component = header_config.sanitize_component(doc_id or "document")
    out_dir = os.path.join(base_dir, doc_component)
    header_config._ensure_dir(out_dir)

    audit_rows: List[Dict[str, Any]] = []
    threshold = header_config.ACCEPT_SCORE_THRESHOLD
    for entry in pages_debug:
        page_idx, _snapshot, _page_text, line_records = _unpack_page_debug_entry(entry)
        for row in line_records or []:
            text_norm = (row.get("text_norm") or "").strip()
            if not rx.match(text_norm):
                continue
            style = row.get("style") or {}
            breakdown = score_header_candidate_debug(text_norm, style=style)
            drop_reason = row.get("drop_reason")
            audit_rows.append(
                {
                    "page": int(page_idx) + 1,
                    "line_idx": row.get("line_idx"),
                    "text_norm": text_norm,
                    "regex_hits": breakdown.regex_hits,
                    "total_score": breakdown.total,
                    "threshold": threshold,
                    "accepted": bool(breakdown.total >= threshold and not drop_reason),
                    "drop_reason": drop_reason,
                    "x_left": style.get("x_left"),
                    "font_size": style.get("font_size"),
                    "bold": style.get("bold"),
                }
            )

    with open(os.path.join(out_dir, "appendix_audit.json"), "w", encoding="utf-8") as fh:
        json.dump(audit_rows, fh, ensure_ascii=False, indent=2)


def write_header_candidate_audit(
    doc_id: str,
    pages_debug: Iterable[Any],
    results: Iterable[Dict[str, Any]],
    *,
    output_root: Optional[str] = None,
) -> None:
    """Persist a machine-readable snapshot of header candidate scoring."""

    base_dir = (output_root or header_config.CONFIG.get("audit_dir") or "./debug/headers").strip()
    if not base_dir:
        base_dir = "./debug/headers"

    doc_component = header_config.sanitize_component(doc_id)
    out_dir = os.path.join(base_dir, doc_component)
    header_config._ensure_dir(out_dir)

    threshold = float(header_config.ACCEPT_SCORE_THRESHOLD or 2.25)

    def _coerce_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except Exception:
            return None

    snapshot_map: Dict[int, List[dict]] = {}
    page_text_map: Dict[int, str] = {}
    for entry in pages_debug or []:
        page_idx, snapshot, page_text, _line_records = _unpack_page_debug_entry(entry)
        idx = _coerce_int(page_idx)
        if idx is None:
            continue
        snapshot_map[idx] = list(snapshot or [])
        page_text_map[idx] = page_text or ""

    headers_by_page: Dict[int, List[Dict[str, Any]]] = {}
    for result in results or []:
        page_idx = _coerce_int(result.get("page", 0))
        if page_idx is None:
            continue
        page_idx -= 1
        if page_idx is None or page_idx < 0:
            continue
        headers = []
        for header in result.get("headers") or []:
            if not isinstance(header, dict):
                continue
            headers.append({
                "line_idx": header.get("line_idx"),
                "text": header.get("text"),
                "section_number": header.get("section_number"),
                "level": header.get("level"),
                "score": header.get("score"),
                "style": header.get("style"),
            })
        headers_by_page[page_idx] = headers

    selected_keys = set()
    for page_idx, headers in headers_by_page.items():
        for header in headers:
            key = _coerce_int(header.get("line_idx"))
            if key is None:
                continue
            selected_keys.add((page_idx, key))

    all_page_indices = sorted(set(snapshot_map.keys()) | set(headers_by_page.keys()))

    pages_payload: List[Dict[str, Any]] = []
    for page_idx in all_page_indices:
        snapshot = snapshot_map.get(page_idx, [])
        entries: List[Dict[str, Any]] = []
        for cand in snapshot:
            line_idx = cand.get("line_idx")
            coerced_idx = _coerce_int(line_idx)
            breakdown = score_header_candidate_debug(
                cand.get("text_norm") or cand.get("text"), style=cand.get("style") or {}
            )
            selected = (
                (page_idx, coerced_idx) in selected_keys
                if coerced_idx is not None
                else False
            )
            meets_threshold = breakdown.total >= threshold
            if selected:
                decision = "selected"
            elif not meets_threshold:
                decision = "below_threshold"
            else:
                decision = "not_selected"
            entry = {
                "line_idx": line_idx,
                "text": breakdown.text,
                "score": float(breakdown.total),
                "meets_threshold": meets_threshold,
                "decision": decision,
                "section_number": cand.get("section_number"),
                "level": cand.get("level"),
                "style": cand.get("style") or {},
                "partial_scores": breakdown.partial_scores,
                "disqualifiers": breakdown.disqualifiers,
                "regex_hits": breakdown.regex_hits,
            }
            entries.append(entry)

        entries.sort(key=lambda item: item.get("score", 0.0), reverse=True)
        for rank, entry in enumerate(entries, start=1):
            entry["rank"] = rank
            entry["selected"] = entry.get("decision") == "selected"

        page_record: Dict[str, Any] = {
            "page": page_idx + 1,
            "candidate_count": len(entries),
            "candidates": entries,
            "final_headers": headers_by_page.get(page_idx, []),
        }
        text_sample = page_text_map.get(page_idx)
        if text_sample:
            page_record["sample_text"] = text_sample[:4000]

        pages_payload.append(page_record)

    report = {
        "doc": doc_component,
        "threshold": threshold,
        "pages": pages_payload,
    }

    with open(os.path.join(out_dir, "candidate_audit.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)


def write_header_debug_manifest(
    doc_id: str,
    pages_debug: List[Any],
    results: List[Dict[str, Any]],
    *,
    llm_selections: Optional[Dict[int, List[Dict[str, Any]]]] = None,
) -> None:
    if not header_config.CONFIG.get("debug"):
        return

    base_dir = header_config.CONFIG.get("debug_dir") or header_config.DEBUG_DIR or "./_debug/headers"
    doc_component = header_config.sanitize_component(doc_id or "document")
    out_dir = os.path.join(base_dir, doc_component)
    header_config._ensure_dir(base_dir)
    header_config._ensure_dir(out_dir)

    llm_selections = llm_selections or {}
    selection_map: Dict[int, List[Dict[str, Any]]] = {}
    for idx, payload in llm_selections.items():
        if not isinstance(payload, list):
            continue
        filtered: List[Dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict):
                filtered.append(dict(item))
        if filtered:
            selection_map[idx] = filtered

    headers_by_page: Dict[int, List[Dict[str, Any]]] = {}
    for result in results or []:
        try:
            page_idx = int(result.get("page", 0)) - 1
        except Exception:
            continue
        if page_idx < 0:
            continue
        page_headers = [
            dict(header)
            for header in (result.get("headers") or [])
            if isinstance(header, dict)
        ]
        headers_by_page[page_idx] = page_headers

    threshold = header_config.ACCEPT_SCORE_THRESHOLD
    manifest_pages: List[Dict[str, Any]] = []

    for entry in pages_debug:
        page_idx, snapshot, _page_text, _line_records = _unpack_page_debug_entry(entry)
        entries: List[Dict[str, Any]] = []
        for cand in snapshot or []:
            breakdown = score_header_candidate_debug(
                cand.get("text_norm") or cand.get("text"), style=cand.get("style") or {}
            )
            entries.append(
                {
                    "line_idx": cand.get("line_idx"),
                    "text": breakdown.text,
                    "score": float(breakdown.total),
                    "accepted": breakdown.total >= threshold,
                    "disqualifiers": breakdown.disqualifiers,
                    "regex_hits": breakdown.regex_hits,
                }
            )

        entries.sort(key=lambda item: item.get("score", 0.0), reverse=True)

        llm_items = selection_map.get(page_idx) or []
        llm_lines = sorted(
            {
                int(item.get("line_idx"))
                for item in llm_items
                if isinstance(item, dict) and item.get("line_idx") is not None
            }
        )

        headers = headers_by_page.get(page_idx) or []
        page_entry = {
            "page": page_idx + 1,
            "directory": f"page_{page_idx:04d}",
            "candidate_count": len(snapshot or []),
            "llm_selected": llm_lines,
            "final_headers": [
                {
                    "line_idx": header.get("line_idx"),
                    "text": header.get("text"),
                    "section_number": header.get("section_number"),
                    "score": header.get("score"),
                    "level": header.get("level"),
                }
                for header in headers
            ],
            "top_candidates": entries[: min(len(entries), 8)],
        }
        manifest_pages.append(page_entry)

    manifest = {
        "doc": doc_id or "document",
        "threshold": threshold,
        "pages": manifest_pages,
    }

    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
