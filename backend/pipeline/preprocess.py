# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import importlib
from typing import List, Dict, Any, Iterable, Optional

# PDF extraction wrapper
from ..ingest.pdf_extract import extract as pdf_extract

# v1.7 header helpers
from ..parse.header_config import CONFIG
from ..parse.header_page_mode import select_candidates, build_adjudication_prompt
from ..parse.header_detector import is_header_line

# Optional legacy section chunker (keep compatibility)
try:
    from ..rag.chunker import sections_from_lines, yield_section_chunks  # type: ignore
except Exception:
    sections_from_lines = None
    yield_section_chunks = None

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
) -> Iterable[Dict[str, Any]]:
    """
    Build section-bounded chunks using lines + styles when available.
    Falls back to simple size-based chunking if the legacy chunker isn't present.
    """
    data = pdf_extract(pdf_path, sidecar_dir)
    pages_lines = data.get("pages_lines") or []
    page_line_styles = data.get("page_line_styles") or None

    if callable(sections_from_lines) and callable(yield_section_chunks):
        secs = sections_from_lines(pages_lines, page_line_styles)  # type: ignore
        for ch in yield_section_chunks(secs, tok_budget_chars, overlap_lines):  # type: ignore
            yield ch
        return

    # Fallback: size-based chunking
    linear = data.get("pages_linear") or []
    text = "\n".join(linear)
    buf, size, idx = [], 0, 0
    for line in text.splitlines():
        l = (line or "") + "\n"
        if size + len(l) > tok_budget_chars and buf:
            yield {
                "text": "".join(buf).strip(),
                "section_title": "Document",
                "section_id": "1",
                "page_start": 1,
                "page_end": max(1, len(linear)),
                "chunk_index_in_section": idx,
                "chunk_type": "paragraph",
            }
            idx += 1
            buf = buf[-overlap_lines:] if overlap_lines > 0 else []
            size = sum(len(t) for t in buf)
        buf.append(l)
        size += len(l)
    if buf:
        yield {
            "text": "".join(buf).strip(),
            "section_title": "Document",
            "section_id": "1",
            "page_start": 1,
            "page_end": max(1, len(linear)),
            "chunk_index_in_section": idx,
            "chunk_type": "paragraph",
        }

def standard_pre_chunks(
    pdf_path: str,
    sidecar_dir: Optional[str] = None,
    tok_budget_chars: int = 6400,
    overlap_lines: int = 3,
) -> Iterable[Dict[str, Any]]:
    """Legacy entry that routes to the section-bounded chunker."""
    for ch in section_bounded_chunks_from_pdf(pdf_path, sidecar_dir, tok_budget_chars, overlap_lines):
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
) -> List[Dict[str, Any]]:
    """
    Deterministic-first header detection, page-by-page, with optional LLM adjudication.
    Returns: [{"page": N, "headers": [{"line_idx","text","section_number","level","score","style"}]}]
    """
    results: List[Dict[str, Any]] = []
    for pi, lines in enumerate(pages_lines or []):
        styles = page_line_styles[pi] if page_line_styles and pi < len(page_line_styles) else [{} for _ in lines]
        candidates = select_candidates(lines, styles)

        det = [c for c in candidates if c["score"] >= CONFIG.get("accept_score_threshold", 2.0)]
        ambiguous = [c for c in candidates if CONFIG.get("ambiguous_score_threshold", 1.0) <= c["score"] < CONFIG.get("accept_score_threshold", 2.0)]
        final = det[:]

        need_llm = CONFIG.get("llm_enabled", True) and (ambiguous or len(candidates) > CONFIG.get("max_candidates_per_page", 40)//2)
        if need_llm and llm_client is not None:
            user_msg = {
                "role": "user",
                "content": build_adjudication_prompt(
                    page_texts[pi] if page_texts and pi < len(page_texts) else "\n".join(lines),
                    candidates,
                    CONFIG.get("context_chars_per_candidate", 700),
                ),
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
    return results
