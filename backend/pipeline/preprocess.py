# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import importlib
import copy
from typing import List, Dict, Any, Iterable, Optional, Tuple

# PDF extraction wrapper
from ..ingest.pdf_extract import extract as pdf_extract

# v1.7 header helpers
from ..parse.header_config import CONFIG
from ..parse.header_page_mode import (
    select_candidates,
    build_adjudication_prompt,
    dump_appendix_audit,
    write_header_candidate_audit,
    write_header_debug_manifest,
    write_page_debug,
)
from ..parse.header_detector import is_header_line
from ..state import get_state

# Optional legacy section chunker (keep compatibility)
try:
    from ..rag.chunker import sections_from_lines  # type: ignore
except Exception:
    sections_from_lines = None

# ---------- Internal helpers for section-aware chunking ----------

def _collect_lines_between(
    pages_lines: List[List[str]],
    start: Tuple[int, int],
    end: Tuple[int, int],
) -> Tuple[List[str], int]:
    """Return lines between two (page_idx, line_idx) positions and last page touched."""
    if not pages_lines:
        return [], 0

    max_page = len(pages_lines) - 1
    start_page = max(0, min(start[0], max_page))
    end_page = max(0, min(end[0], max_page))
    start_line = max(0, start[1])
    end_line = max(0, end[1])

    if end_page < start_page or (end_page == start_page and end_line <= start_line):
        return [], start_page

    collected: List[str] = []
    last_page = start_page
    for page_idx in range(start_page, end_page + 1):
        lines = pages_lines[page_idx] if 0 <= page_idx < len(pages_lines) else []
        begin = start_line if page_idx == start_page else 0
        finish = end_line if page_idx == end_page else len(lines)
        begin = max(0, min(begin, len(lines)))
        finish = max(0, min(finish, len(lines)))
        if finish < begin:
            finish = begin
        segment = lines[begin:finish]
        if segment:
            collected.extend(segment)
            last_page = page_idx
    return collected, last_page


def _sections_from_detected_headers(
    pages_lines: List[List[str]],
    detected: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Build section descriptors from stored header detection output."""
    if not pages_lines or not detected:
        return []

    entries: List[Dict[str, Any]] = []
    for page_block in detected:
        page = int(page_block.get("page", 0) or 0)
        headers = page_block.get("headers") or []
        if page < 1 or page > len(pages_lines) or not headers:
            continue
        for header in headers:
            try:
                line_idx = int(header.get("line_idx", -1))
            except Exception:
                continue
            if line_idx < 0:
                continue
            entries.append(
                {
                    "page": page,
                    "line_idx": line_idx,
                    "text": (header.get("text") or "").strip(),
                    "section_number": (header.get("section_number") or "").strip(),
                    "level": header.get("level"),
                }
            )

    if not entries:
        return []

    entries.sort(key=lambda item: (item["page"], item["line_idx"]))
    sections: List[Dict[str, Any]] = []

    # Optional preamble before the first detected header
    first = entries[0]
    first_page_idx = max(0, first["page"] - 1)
    first_line_idx = max(0, first["line_idx"])
    pre_lines, pre_last_page = _collect_lines_between(
        pages_lines,
        (0, 0),
        (first_page_idx, first_line_idx),
    )
    if pre_lines:
        sections.append(
            {
                "title": "Preamble",
                "id": "0",
                "section_number": "0",
                "content": pre_lines,
                "page_start": 1,
                "page_end": pre_last_page + 1,
                "heading_level": 1,
                "source_page": 1,
                "source_line_idx": 0,
                "sequence_index": 0,
            }
        )

    doc_last_page = len(pages_lines) - 1
    doc_last_line = len(pages_lines[doc_last_page]) if doc_last_page >= 0 else 0

    for idx, entry in enumerate(entries, start=1):
        page_idx = max(0, entry["page"] - 1)
        page_lines = pages_lines[page_idx] if 0 <= page_idx < len(pages_lines) else []
        if page_lines:
            clamped_idx = max(0, min(entry["line_idx"], len(page_lines) - 1))
        else:
            clamped_idx = 0

        header_text = entry["text"] or (page_lines[clamped_idx].strip() if 0 <= clamped_idx < len(page_lines) else "")
        next_entry = entries[idx] if idx < len(entries) else None
        if next_entry:
            next_page_idx = max(0, next_entry["page"] - 1)
            next_line_idx = max(0, next_entry["line_idx"])
            end_pos = (next_page_idx, next_line_idx)
        else:
            end_pos = (doc_last_page, doc_last_line)

        start_after_header = (page_idx, clamped_idx + 1)
        between_lines, last_page = _collect_lines_between(
            pages_lines,
            start_after_header,
            end_pos,
        )

        content_lines = [header_text] if header_text else []
        if between_lines:
            content_lines.extend(between_lines)

        if not content_lines:
            continue

        section_number = entry["section_number"] or str(idx)
        sections.append(
            {
                "title": header_text or f"Section {section_number}",
                "id": section_number,
                "section_number": section_number,
                "content": content_lines,
                "page_start": entry["page"],
                "page_end": max(entry["page"], last_page + 1),
                "heading_level": entry.get("level"),
                "source_page": entry["page"],
                "source_line_idx": entry["line_idx"],
                "sequence_index": idx,
            }
        )

    return sections


def _emit_section_chunk(
    section: Dict[str, Any], buf: List[Tuple[str, Optional[int]]], idx: int
) -> Dict[str, Any]:
    text = "".join(part for part, _ in buf).strip()
    line_indices = [line_idx for _, line_idx in buf if line_idx is not None]
    line_span: Optional[Tuple[int, int]] = None
    if line_indices:
        line_span = (min(line_indices), max(line_indices))
    token_estimate = approximate_tokens(text)
    char_count = len(text)
    line_count = len(line_indices)
    page_start = int(section.get("page_start", 1) or 1)
    page_end = int(section.get("page_end", section.get("page_start", 1)) or 1)
    pages = list(range(page_start, page_end + 1)) if page_end >= page_start else [page_start]
    chunk_id = f"{section.get('id', 'section')}|{idx:03d}"
    return {
        "text": text,
        "section_title": section.get("title", "Document"),
        "section_id": section.get("id", "1"),
        "section_number": section.get("section_number"),
        "section_sequence_index": section.get("sequence_index"),
        "page_start": page_start,
        "page_end": page_end,
        "pages": pages,
        "chunk_index_in_section": idx,
        "chunk_type": "paragraph",
        "heading_level": section.get("heading_level"),
        "section_source_page": section.get("source_page"),
        "section_source_line_idx": section.get("source_line_idx"),
        "section_line_span": line_span,
        "char_count": char_count,
        "line_count": line_count,
        "token_estimate": token_estimate,
        "chunk_id": chunk_id,
        "resolution": "legacy",
    }


def _yield_chunks_from_sections(
    sections: List[Dict[str, Any]],
    tok_budget_chars: int,
    overlap_lines: int,
) -> Iterable[Dict[str, Any]]:
    for section in sections:
        lines = section.get("content") or []
        if not lines:
            continue
        buf: List[Tuple[str, Optional[int]]] = []
        size = 0
        idx = 0
        for local_idx, line in enumerate(lines):
            segment = (line or "") + "\n"
            if size + len(segment) > tok_budget_chars and buf:
                yield _emit_section_chunk(section, buf, idx)
                idx += 1
                buf = buf[-overlap_lines:] if overlap_lines > 0 else []
                size = sum(len(part) for part, _ in buf)
            buf.append((segment, local_idx))
            size += len(segment)
        if buf:
            yield _emit_section_chunk(section, buf, idx)
# ---------- Public helpers expected by routes & passes ----------

def extract_pages_with_layout(pdf_path: str, sidecar_dir: Optional[str] = None) -> Dict[str, Any]:
    """Returns pages_linear, pages_lines, page_line_styles, layout metadata."""
    return pdf_extract(pdf_path, sidecar_dir)

def load_document_to_text_pages(pdf_path: str, sidecar_dir: Optional[str] = None) -> List[str]:
    """Legacy helper: return a list of page strings."""
    data = extract_pages_with_layout(pdf_path, sidecar_dir)
    return data.get("pages_linear") or []

def approximate_tokens(text: str) -> int:
    """Crude token estimate (~4 chars/token). Keep name/signature stable for passes.py."""
    if not text:
        return 0
    return max(1, len(text) // 4)

def section_bounded_chunks_from_pdf(
    pdf_path: str,
    sidecar_dir: Optional[str] = None,
    tok_budget_chars: int = 6400,
    overlap_lines: int = 3,
    session_id: Optional[str] = None,
) -> Iterable[Dict[str, Any]]:
    """
    Build section-bounded chunks using lines + styles when available.
    Falls back to simple size-based chunking if the legacy chunker isn't present.
    """
    data = pdf_extract(pdf_path, sidecar_dir)
    pages_lines = data.get("pages_lines") or []
    page_line_styles = data.get("page_line_styles") or None

    session_sections: List[Dict[str, Any]] = []
    if session_id:
        state = get_state(session_id)
        if state and state.headers:
            session_sections = _sections_from_detected_headers(pages_lines, state.headers)

    if session_sections:
        for chunk in _yield_chunks_from_sections(session_sections, tok_budget_chars, overlap_lines):
            yield chunk
        return

    if callable(sections_from_lines):
        secs = sections_from_lines(pages_lines, page_line_styles)  # type: ignore
        if secs:
            for chunk in _yield_chunks_from_sections(secs, tok_budget_chars, overlap_lines):
                yield chunk
            return

    # Fallback: size-based chunking
    linear = data.get("pages_linear") or []
    text = "\n".join(linear)
    buf: List[Tuple[str, Optional[int]]] = []
    size, idx, line_idx = 0, 0, 0
    for line in text.splitlines():
        l = (line or "") + "\n"
        if size + len(l) > tok_budget_chars and buf:
            yield _emit_section_chunk(
                {
                    "title": "Document",
                    "id": "1",
                    "page_start": 1,
                    "page_end": max(1, len(linear)),
                    "section_number": "1",
                    "sequence_index": 0,
                },
                buf,
                idx,
            )
            idx += 1
            buf = buf[-overlap_lines:] if overlap_lines > 0 else []
            size = sum(len(part) for part, _ in buf)
        buf.append((l, line_idx))
        size += len(l)
        line_idx += 1
    if buf:
        yield _emit_section_chunk(
            {
                "title": "Document",
                "id": "1",
                "page_start": 1,
                "page_end": max(1, len(linear)),
                "section_number": "1",
                "sequence_index": 0,
            },
            buf,
            idx,
        )

def standard_pre_chunks(
    pdf_path: str,
    sidecar_dir: Optional[str] = None,
    tok_budget_chars: int = 6400,
    overlap_lines: int = 3,
    session_id: Optional[str] = None,
) -> Iterable[Dict[str, Any]]:
    """Legacy entry that routes to the section-bounded chunker."""
    for ch in section_bounded_chunks_from_pdf(
        pdf_path,
        sidecar_dir,
        tok_budget_chars,
        overlap_lines,
        session_id=session_id,
    ):
        yield ch

# ---------- RFQ header prompt accessor (hot-reloads) ----------

def _get_header_system_prompt() -> str:
    """Reload and return the current RFQ header system prompt from backend.prompts."""
    try:
        from backend import prompts as _prompts  # type: ignore
    except Exception:
        import backend.prompts as _prompts  # type: ignore
    try:
        importlib.reload(_prompts)
    except Exception:
        pass
    sys_prompt = getattr(_prompts, "HEADER_DETECTION_SYSTEM", "").strip()
    try:
        print("[HeaderPrompt] Using system prompt:", sys_prompt[:120].replace("\n", " "))
    except Exception:
        pass
    return sys_prompt

# ---------- v1.7 page-mode header detection ----------

async def detect_headers_page_mode(
    pages_lines: List[List[str]],
    page_line_styles: Optional[List[List[dict]]],
    page_texts: Optional[List[str]],
    llm_client,
    doc_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Deterministic-first header detection, page-by-page, with optional LLM adjudication.
    Returns: [{"page": N, "headers": [{"line_idx","text","section_number","level","score","style"}]}]
    """
    results: List[Dict[str, Any]] = []
    debug_snapshots: List[Tuple[int, List[dict], str]] = []
    llm_selections: Dict[int, List[Dict[str, Any]]] = {}
    doc_tag = doc_id or "document"
    for pi, lines in enumerate(pages_lines or []):
        styles = page_line_styles[pi] if page_line_styles and pi < len(page_line_styles) else [{} for _ in lines]
        candidates = select_candidates(lines, styles)
        page_text = (
            page_texts[pi]
            if page_texts and pi < len(page_texts)
            else "\n".join(lines)
        )
        snapshot = [copy.deepcopy(c) for c in candidates]
        debug_snapshots.append((pi, snapshot, page_text))
        write_page_debug(doc_tag, pi, page_text, snapshot)

        det = [c for c in candidates if c["score"] >= CONFIG.get("accept_score_threshold", 2.0)]
        ambiguous = [c for c in candidates if CONFIG.get("ambiguous_score_threshold", 1.0) <= c["score"] < CONFIG.get("accept_score_threshold", 2.0)]
        final = det[:]

        need_llm = CONFIG.get("llm_enabled", True) and (ambiguous or len(candidates) > CONFIG.get("max_candidates_per_page", 40)//2)
        if need_llm and llm_client is not None:
            page_prompt = build_adjudication_prompt(
                page_text,
                candidates,
                CONFIG.get("context_chars_per_candidate", 700),
            )
            write_page_debug(doc_tag, pi, page_text, snapshot, llm_prompt=page_prompt)
            user_msg = {
                "role": "user",
                "content": page_prompt,
            }
            sys_prompt = _get_header_system_prompt()
            try:
                resp = await llm_client.chat(
                    [{"role": "system", "content": sys_prompt}, user_msg],
                    temperature=CONFIG.get("llm_temperature", 0.0),
                    max_tokens=1024,
                )
                payload = resp.get("json") or resp.get("data") or resp.get("text")
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except Exception:
                        payload = []
                if isinstance(payload, list) and (len(payload) >= max(1, int(len(det) * 0.6))):
                    for item in payload:
                        try:
                            idx = int(item.get("line_idx"))
                            name = (item.get("section_name") or "").strip()
                            num = (item.get("section_number") or "").strip()
                            if 0 <= idx < len(lines) and name:
                                level = next((c["level"] for c in candidates if c["line_idx"] == idx), 3)
                                final.append({
                                    "line_idx": idx,
                                    "text": lines[idx].strip(),
                                    "section_number": num,
                                    "level": level,
                                    "score": 3.0,
                                    "style": {},
                                })
                        except Exception:
                            continue
                selections = payload if isinstance(payload, list) else []
                if selections:
                    llm_selections[pi] = [
                        dict(item) for item in selections if isinstance(item, dict)
                    ]
                write_page_debug(
                    doc_tag,
                    pi,
                    page_text,
                    snapshot,
                    llm_prompt=page_prompt,
                    llm_json=selections,
                )
            except Exception:
                pass

        # dedup by line_idx
        seen = set()
        ordered = []
        for c in sorted(final, key=lambda x: x["line_idx"]):
            if c["line_idx"] in seen:
                continue
            seen.add(c["line_idx"])
            ordered.append(c)

        results.append({"page": pi + 1, "headers": ordered})

    dump_appendix_audit(doc_tag, debug_snapshots)
    write_header_debug_manifest(
        doc_tag,
        debug_snapshots,
        results,
        llm_selections=llm_selections,
    )
    write_header_candidate_audit(
        doc_tag,
        debug_snapshots,
        results,
    )
    return results
