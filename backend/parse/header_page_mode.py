# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional, Iterable
import re
import os
import csv
import json

try:
    from rapidfuzz.fuzz import ratio as fuzz_ratio
except Exception:
    import difflib
    def fuzz_ratio(a, b): return int(100 * difflib.SequenceMatcher(None, a or "", b or "").ratio())

from .header_detector import score_header_candidate, score_header_candidate_debug
from .header_levels import map_font_sizes_to_levels, infer_heading_level
from .header_config import CONFIG

MEASURE_RX = re.compile(r'\b(?:\d{1,4}(?:\.\d+)?)(?:\s*(?:mm|cm|m|in|inch|ft|°c|°f|a|v|hz|psi|kpa|ip\d{2}))\b', re.I)
ADDRESS_RX = re.compile(r'\b(?:Street|St\.|Road|Rd\.|Drive|Dr\.|Ave\.|Avenue|Suite|USA|Tel|Fax)\b', re.I)
TOO_LONG_RX = re.compile(r'^\s*.{161,}\s*$')
SAFE_COMPONENT_RX = re.compile(r"[^A-Za-z0-9._-]+")

def _caps_ratio(s: str) -> float:
    letters = [c for c in s if c.isalpha()]
    return (sum(c.isupper() for c in letters) / max(1, len(letters))) if letters else 0.0

def _looks_like_header_text(txt: str) -> bool:
    if not (6 <= len(txt) <= 160):       # keep in sync with header_detector
        return False
    if ADDRESS_RX.search(txt):
        return False
    if MEASURE_RX.search(txt):
        # Measurements often appear in specs lines; penalize
        return False
    if TOO_LONG_RX.match(txt):
        return False
    return True

def select_candidates(page_lines: List[str], page_styles: List[dict]) -> List[dict]:
    cands = []
    font_sizes = [(s or {}).get("font_size") for s in (page_styles or []) if (s or {}).get("font_size") is not None]
    size_map = map_font_sizes_to_levels(font_sizes, max_levels=4) if CONFIG.get("use_font_clusters", True) else {}

    for idx, raw in enumerate(page_lines or []):
        line = (raw or "").strip()
        if not line:
            continue

        style = (page_styles[idx] if page_styles and idx < len(page_styles) else {}) or {}
        if not _looks_like_header_text(line):
            continue

        s = score_header_candidate(line, style)
        if s < CONFIG.get("ambiguous_score_threshold", 1.10):
            continue

        caps = _caps_ratio(line)
        # Light boost for ALLCAPS or Title Case
        if caps >= 0.75:
            s += 0.25

        # Extract a plausible section number prefix if it exists
        m = re.search(r"^\s*([A-Z]|Appendix\s+[A-Z]|\d+(?:\.\d+)*|\d+\))", line, flags=re.IGNORECASE)
        section_number = (m.group(1) if m else "").strip()

        level = infer_heading_level(style.get("font_size"), section_number, size_map)
        cands.append({
            "line_idx": idx,
            "text": line,
            "style": {
                "font_sigma_rank": style.get("font_sigma_rank"),
                "bold": style.get("bold"),
                "caps_ratio": caps,
                "font_size": style.get("font_size"),
            },
            "score": s,
            "section_number": section_number,
            "level": level,
        })

    # Dedup near-duplicates (within a page) by fuzzy ratio
    cands.sort(key=lambda x: (-x["score"], x["line_idx"]))
    deduped, seen_text = [], []
    for c in cands:
        if seen_text and fuzz_ratio(seen_text[-1], c["text"]) >= CONFIG.get("dedup_fuzzy_threshold", 90):
            # keep the higher score already in deduped
            continue
        deduped.append(c)
        seen_text.append(c["text"])

    return deduped[: CONFIG.get("max_candidates_per_page", 40)]


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
    ctxs  = [f"[{c['line_idx']}]: {window_around_line(blob, c['text'], chars=context_chars)}" for c in candidates]

    return (
        "You are validating section headings in an engineering RFQ/spec. "
        "Return ONLY JSON list: [{\"section_number\":\"\",\"section_name\":\"\",\"line_idx\":0}]. No prose.\n\n"
        "CANDIDATE_LINES:\n" + "\n".join(lines) + "\n\n" +
        "PAGE_TEXT_SNIPPETS:\n" + "\n".join(ctxs)
    )


def _ensure_dir(path: str) -> None:
    if path:
        os.makedirs(path, exist_ok=True)


def _sanitize_doc_id(value: Optional[str]) -> str:
    base = (value or "document").strip() or "document"
    cleaned = SAFE_COMPONENT_RX.sub("_", base)
    return cleaned or "document"


def _dump_page_debug(
    doc_id: str,
    page_idx: int,
    page_text: str,
    candidates: List[dict],
    llm_prompt: Optional[str] = None,
    llm_json: Optional[List[Dict[str, Any]]] = None,
) -> None:
    if not CONFIG.get("debug"):
        return

    base_dir = CONFIG.get("debug_dir", "./_debug/headers") or "./_debug/headers"

    _ensure_dir(base_dir)

    out_dir = os.path.join(base_dir, doc_id or "document", f"page_{page_idx:04d}")
    _ensure_dir(out_dir)

    csv_path = os.path.join(out_dir, "candidates.csv")
    threshold = CONFIG.get("accept_score_threshold", 2.25)
    breakdowns: List[Dict[str, Any]] = []
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "line_idx",
                "text",
                "regex_hits",
                "numbering_depth",
                "font_size",
                "bold",
                "caps",
                "disqualifiers",
                "partial_scores",
                "total_score",
                "accepted",
                "threshold",
            ]
        )
        for cand in candidates:
            breakdown = score_header_candidate_debug(
                cand.get("text"), style=cand.get("style") or {}
            )
            accepted = breakdown.total >= threshold
            entry = {
                "line_idx": cand.get("line_idx"),
                "text": breakdown.text,
                "regex_hits": breakdown.regex_hits,
                "numbering_depth": breakdown.numbering_depth,
                "font_size": breakdown.font_size,
                "bold": breakdown.bold,
                "caps": breakdown.caps,
                "disqualifiers": breakdown.disqualifiers,
                "partial_scores": breakdown.partial_scores,
                "score": float(breakdown.total),
                "accepted": accepted,
                "threshold": threshold,
            }
            breakdowns.append(entry)
            writer.writerow(
                [
                    entry["line_idx"],
                    entry["text"],
                    " | ".join(entry["regex_hits"]),
                    entry["numbering_depth"],
                    entry["font_size"],
                    entry["bold"],
                    entry["caps"],
                    " | ".join(entry["disqualifiers"]),
                    json.dumps(entry["partial_scores"], ensure_ascii=False),
                    f"{entry['score']:.2f}",
                    entry["accepted"],
                    entry["threshold"],
                ]
            )

    llm_indices = set()
    if llm_json:
        for item in llm_json:
            try:
                idx = int(item.get("line_idx"))
            except Exception:
                continue
            llm_indices.add(idx)

    for entry in breakdowns:
        entry["llm_selected"] = bool(llm_indices and entry["line_idx"] in llm_indices)

    analysis_path = os.path.join(out_dir, "analysis.json")
    with open(analysis_path, "w", encoding="utf-8") as fh:
        json.dump(
            sorted(breakdowns, key=lambda item: item.get("score", 0.0), reverse=True),
            fh,
            ensure_ascii=False,
            indent=2,
        )

    with open(os.path.join(out_dir, "candidates.json"), "w", encoding="utf-8") as fh:
        json.dump(candidates, fh, ensure_ascii=False, indent=2)

    with open(os.path.join(out_dir, "page.txt"), "w", encoding="utf-8") as fh:
        fh.write(page_text)

    if llm_prompt is not None:
        with open(os.path.join(out_dir, "llm_prompt.txt"), "w", encoding="utf-8") as fh:
            fh.write(llm_prompt)

    if llm_json is not None:
        with open(os.path.join(out_dir, "llm_selection.json"), "w", encoding="utf-8") as fh:
            json.dump(llm_json, fh, ensure_ascii=False, indent=2)


def write_page_debug(
    doc_id: str,
    page_idx: int,
    page_text: str,
    candidates: List[dict],
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
        llm_prompt=llm_prompt,
        llm_json=llm_json,
    )


def dump_appendix_audit(
    doc_id: str,
    pages_debug: List[Tuple[int, List[dict], str]],
) -> None:
    if not CONFIG.get("debug"):
        return

    rx = re.compile(r"^\s*(?:Appendix\s+[A-Za-z]|[A-Za-z]\d+\.)")
    base_dir = CONFIG.get("debug_dir", "./_debug/headers") or "./_debug/headers"

    _ensure_dir(base_dir)

    out_dir = os.path.join(base_dir, doc_id or "document")
    _ensure_dir(out_dir)

    audit_rows: List[Dict[str, Any]] = []
    threshold = CONFIG.get("accept_score_threshold", 2.25)
    for page_idx, cand_list, _page_text in pages_debug:
        for cand in cand_list:
            txt = (cand.get("text") or "").strip()
            if not rx.match(txt):
                continue
            breakdown = score_header_candidate_debug(txt, style=cand.get("style") or {})
            audit_rows.append(
                {
                    "page": page_idx + 1,
                    "line_idx": cand.get("line_idx"),
                    "text": txt,
                    "regex_hits": breakdown.regex_hits,
                    "total": breakdown.total,
                    "accepted": breakdown.total >= threshold,
                    "partial_scores": breakdown.partial_scores,
                    "disqualifiers": breakdown.disqualifiers,
                }
            )

    with open(os.path.join(out_dir, "appendix_audit.json"), "w", encoding="utf-8") as fh:
        json.dump(audit_rows, fh, ensure_ascii=False, indent=2)


def write_header_candidate_audit(
    doc_id: str,
    pages_debug: Iterable[Tuple[int, List[dict], str]],
    results: Iterable[Dict[str, Any]],
    *,
    output_root: Optional[str] = None,
) -> None:
    """Persist a machine-readable snapshot of header candidate scoring.

    Unlike the debug artefacts, this runs for every request so that operators
    can inspect ranking decisions even when debug mode is disabled.
    """

    base_dir = (output_root or CONFIG.get("audit_dir") or "./debug/headers").strip()
    if not base_dir:
        base_dir = "./debug/headers"

    doc_component = _sanitize_doc_id(doc_id)
    out_dir = os.path.join(base_dir, doc_component)
    _ensure_dir(out_dir)

    threshold = float(CONFIG.get("accept_score_threshold", 2.25) or 2.25)

    def _coerce_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except Exception:
            return None

    snapshot_map: Dict[int, List[dict]] = {}
    page_text_map: Dict[int, str] = {}
    for page_idx, snapshot, page_text in pages_debug or []:
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
                cand.get("text"), style=cand.get("style") or {}
            )
            selected = (
                (page_idx, coerced_idx) in selected_keys
                if coerced_idx is not None
                else False
            )
            meets_threshold = breakdown.total >= threshold
            decision = "selected" if selected else (
                "below_threshold" if not selected and not meets_threshold else "not_selected"
            )
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
    pages_debug: List[Tuple[int, List[dict], str]],
    results: List[Dict[str, Any]],
    *,
    llm_selections: Optional[Dict[int, List[Dict[str, Any]]]] = None,
) -> None:
    if not CONFIG.get("debug"):
        return

    base_dir = CONFIG.get("debug_dir", "./_debug/headers") or "./_debug/headers"
    _ensure_dir(base_dir)

    out_dir = os.path.join(base_dir, doc_id or "document")
    _ensure_dir(out_dir)

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
        page_headers = [dict(header) for header in (result.get("headers") or []) if isinstance(header, dict)]
        headers_by_page[page_idx] = page_headers

    threshold = CONFIG.get("accept_score_threshold", 2.25)
    manifest_pages: List[Dict[str, Any]] = []

    for page_idx, snapshot, _page_text in pages_debug:
        entries: List[Dict[str, Any]] = []
        for cand in snapshot or []:
            breakdown = score_header_candidate_debug(cand.get("text"), style=cand.get("style") or {})
            entry = {
                "line_idx": cand.get("line_idx"),
                "text": breakdown.text,
                "score": float(breakdown.total),
                "accepted": breakdown.total >= threshold,
                "disqualifiers": breakdown.disqualifiers,
                "regex_hits": breakdown.regex_hits,
            }
            entries.append(entry)

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
