"""Deterministic PDF header extraction without LLM dependencies."""
from __future__ import annotations

import base64
import logging
import os
import re
from statistics import median
from typing import Any, Dict, List, Optional, Sequence, Tuple

from backend.audit.preprocess_writer import candidate_to_dict, final_to_dict
from backend.headers.preprocess_pipeline import run_header_pipeline

from flask import Blueprint, jsonify, request

try:
    import fitz  # type: ignore[attr-defined]
except ImportError as exc:  # pragma: no cover - dependency error surfaced at runtime
    raise RuntimeError("PyMuPDF (fitz) is required for /api/pdf/headers") from exc

bp = Blueprint("pdf_headers", __name__)
log = logging.getLogger(__name__)

_NUMBERED_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s+(.+)$")
_ALL_CAPS_RE = re.compile(r"^[A-Z0-9][A-Z0-9 \-–—:&/()]+$")


def _load_session_pdf(session_id: str, pdf_path: Optional[str] = None) -> bytes:
    """Return PDF bytes for an uploaded session or explicit path."""
    if not session_id and not pdf_path:
        raise ValueError("Session id or pdf_path required for session extraction")

    if pdf_path:
        candidate = str(pdf_path)
    else:
        uploads_dir = os.getenv("UPLOAD_FOLDER", "uploads")
        candidate = os.path.join(uploads_dir, f"{session_id}.pdf")

    if not os.path.isfile(candidate):
        raise ValueError(f"PDF not found at {candidate}")

    with open(candidate, "rb") as handle:
        data = handle.read()
    log.info("/api/pdf/headers loaded session file '%s' (%d bytes)", candidate, len(data))
    return data


def _decode_pdf_bytes(*, allow_session: bool = False) -> bytes:
    """Return raw PDF bytes from multipart upload, JSON data URL, or session id."""
    if "file" in request.files:
        upload = request.files["file"]
        data = upload.read()
        log.info(
            "/api/pdf/headers received multipart file '%s' (%d bytes)",
            getattr(upload, "filename", "upload.pdf"),
            len(data),
        )
        return data

    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        data_url = payload.get("file_data")
        if isinstance(data_url, str) and data_url.startswith("data:application/pdf;base64,"):
            b64 = data_url.split(",", 1)[1]
            data = base64.b64decode(b64)
            log.info("/api/pdf/headers received base64 data URL (%d bytes)", len(data))
            return data

        if allow_session:
            session_id = str(payload.get("session_id") or payload.get("session") or "")
            pdf_path = payload.get("pdf_path") or payload.get("path")
            if session_id or pdf_path:
                return _load_session_pdf(session_id=session_id, pdf_path=pdf_path)

    raise ValueError("No PDF provided. Use multipart 'file' or JSON body with 'file_data'.")


def _get_toc(doc: "fitz.Document") -> List[Dict[str, Any]]:
    toc_entries: List[Dict[str, Any]] = []
    try:
        for level, page, title in doc.get_toc(simple=True) or []:
            toc_entries.append({"level": int(level), "page": int(page), "text": title or ""})
    except Exception as exc:  # pragma: no cover - PyMuPDF behaviour varies by file
        log.warning("Reading PDF outline failed: %s", exc)
    return toc_entries


def _span_is_bold(span: Dict[str, Any]) -> bool:
    flags = int(span.get("flags", 0))
    font = (span.get("font") or "").lower()
    bold_flag = bool(flags & 2)
    name_hint = any(token in font for token in ("bold", "black", "heavy", "semibold"))
    return bold_flag or name_hint


def _collect_page_lines(page: "fitz.Page") -> List[Dict[str, Any]]:
    blocks = page.get_text("dict").get("blocks", [])
    spans: List[Dict[str, Any]] = []
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            bbox = line.get("bbox", block.get("bbox", [0, 0, 0, 0]))
            for span in line.get("spans", []):
                text = (span.get("text") or "").strip()
                if not text:
                    continue
                spans.append(
                    {
                        "text": text,
                        "font_size": float(span.get("size", 0.0)),
                        "font_name": span.get("font") or "",
                        "is_bold": _span_is_bold(span),
                        "x": float(bbox[0]),
                        "y": float(bbox[1]),
                    }
                )
    spans.sort(key=lambda rec: (rec["y"], rec["x"]))
    return spans


def _rank_font_sizes(pages: Sequence[Sequence[Dict[str, Any]]]) -> Dict[float, int]:
    sizes = sorted({round(line["font_size"], 2) for page in pages for line in page}, reverse=True)
    return {size: index + 1 for index, size in enumerate(sizes)}


def _is_heading_like(text: str) -> bool:
    if not text or len(text) > 160 or text.endswith("."):
        return False
    if _ALL_CAPS_RE.match(text):
        return True
    uppercase = sum(1 for char in text if char.isupper())
    if uppercase >= max(1, len(text) // 3):
        return True
    words = len(text.split())
    return 1 <= words <= 14


def _numbering_depth(text: str) -> int:
    match = _NUMBERED_RE.match(text)
    if not match:
        return 0
    segments = match.group(1).split(".")
    return min(6, len(segments))


def _choose_level(font_rank: int, numbered_level: int) -> int:
    if numbered_level:
        return max(1, min(6, numbered_level))
    return max(1, min(6, font_rank))


def _filter_headers(pages: Sequence[Sequence[Dict[str, Any]]]) -> Tuple[List[Dict[str, Any]], float, Dict[float, int]]:
    if not pages:
        return [], 0.0, {}

    font_rank = _rank_font_sizes(pages)
    if font_rank:
        log.info("Ranked font sizes (largest=1): %s", font_rank)

    all_sizes = [line["font_size"] for page in pages for line in page]
    size_median = median(all_sizes) if all_sizes else 0.0
    log.info("Global font-size median: %.2f", size_median)

    headers: List[Dict[str, Any]] = []
    for page_number, page_lines in enumerate(pages, start=1):
        for line in page_lines:
            text = line["text"].strip()
            if not text:
                continue

            size = round(line["font_size"], 2)
            rank = font_rank.get(size, 999)
            numbered_depth = _numbering_depth(text)
            looks_big = size >= size_median + 0.01
            looks_bold = bool(line["is_bold"])
            heading_like = _is_heading_like(text)

            if not (looks_big or looks_bold or numbered_depth or heading_like):
                continue

            level_font = min(rank, 6) if rank != 999 else 6
            level_number = numbered_depth
            level = _choose_level(level_font, level_number)

            headers.append(
                {
                    "text": text,
                    "page": page_number,
                    "y": round(line["y"], 2),
                    "font_size": size,
                    "font_name": line["font_name"],
                    "is_bold": looks_bold,
                    "level_font": level_font,
                    "level_numbering": level_number,
                    "level": level,
                }
            )

    deduped: List[Dict[str, Any]] = []
    last_key: Tuple[int, str] | None = None
    for header in headers:
        key = (header["page"], header["text"].lower())
        if key != last_key:
            deduped.append(header)
        last_key = key

    log.info("Detected %d candidate headers after heuristics", len(deduped))
    return deduped, size_median, font_rank


def extract_headers(pdf_bytes: bytes) -> Dict[str, Any]:
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        pages: List[List[Dict[str, Any]]] = []
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            pages.append(_collect_page_lines(page))

        headers, size_median, font_rank = _filter_headers(pages)
        toc = _get_toc(doc)

    page_texts: List[str] = []
    for page_lines in pages:
        page_segments = [str(span.get("text") or "").strip() for span in page_lines if span.get("text")]
        page_texts.append("\n".join(segment for segment in page_segments if segment))

    normalized_text = "\n\n".join(segment for segment in page_texts if segment)
    audit_path = os.path.abspath("Epf_Co.preprocess.json")
    doc_meta = {
        "page_count": len(pages),
        "median_font_size": size_median,
        "font_rank": font_rank,
    }
    pipeline_result = run_header_pipeline(
        normalized_text,
        headers,
        doc_meta=doc_meta,
        audit_path=audit_path,
    )
    final_headers = pipeline_result["final_headers"]
    heuristic_candidates = pipeline_result["heuristic_candidates"]
    llm_result = pipeline_result["llm_result"]

    final_payload = [final_to_dict(header) for header in final_headers]
    heuristic_payload = [candidate_to_dict(candidate) for candidate in heuristic_candidates]
    llm_candidates_payload = [candidate_to_dict(candidate) for candidate in llm_result.get("candidates", [])]

    font_rank_list = [{"size": size, "rank": rank} for size, rank in sorted(font_rank.items(), key=lambda item: item[1])]

    llm_parse_error = llm_result.get("parse_error")
    notes = {
        "extraction": "PyMuPDF heuristics merged with LLM header pass.",
        "thresholds": {
            "size_median": size_median,
            "font_ranks": font_rank_list,
        },
        "audit_file": audit_path,
        "llm": {
            "parse_error": llm_parse_error,
            "candidate_count": len(llm_candidates_payload),
        },
    }
    if llm_parse_error:
        notes["llm"]["raw_response_preview"] = (llm_result.get("raw_response") or "")[:200]

    return {
        "ok": True,
        "count": len(final_headers),
        "headers": final_payload,
        "heuristic_headers": headers,
        "heuristic_candidates": heuristic_payload,
        "llm_candidates": llm_candidates_payload,
        "toc": toc,
        "notes": notes,
    }


@bp.post("/api/pdf/headers")
def api_pdf_headers():
    try:
        pdf_bytes = _decode_pdf_bytes()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    try:
        result = extract_headers(pdf_bytes)
        return jsonify(result)
    except Exception as exc:  # pragma: no cover - runtime parsing errors
        log.exception("Deterministic header extraction failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.post("/api/pdf/headers/session")
def api_pdf_headers_session():
    try:
        pdf_bytes = _decode_pdf_bytes(allow_session=True)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    try:
        result = extract_headers(pdf_bytes)
        return jsonify(result)
    except Exception as exc:  # pragma: no cover - runtime parsing errors
        log.exception("Deterministic header extraction failed")
        return jsonify({"ok": False, "error": str(exc)}), 500
