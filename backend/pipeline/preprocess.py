import asyncio
import json
import re
import logging
from typing import List, Dict, Any, Iterable, Optional, Tuple

from pypdf import PdfReader
from docx import Document

log = logging.getLogger("FluidRAG.preprocess")

HEADER_RX = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*(?:[-:]|\s+)\s*(.+?)\s*$")
ALT_HEADER_RX = re.compile(r"^\s*Section\s+(\d+(?:\.\d+)*)\s*[-:]?\s*(.+?)\s*$", re.IGNORECASE)

APPROX_CHARS_PER_TOKEN = 4


def approximate_tokens(text: str) -> int:
    """Rough token estimate assuming ~4 characters per token."""
    return max(1, len(text) // APPROX_CHARS_PER_TOKEN)


def load_document_to_text_pages(path: str) -> List[str]:
    """Return list of page strings. Supports PDF, DOCX, TXT."""
    if path.lower().endswith(".pdf"):
        reader = PdfReader(path)
        pages = [p.extract_text() or "" for p in reader.pages]
        log.debug(f"[preprocess] PDF pages={len(pages)}")
        return pages
    elif path.lower().endswith(".docx"):
        doc = Document(path)
        text = "\n".join([p.text for p in doc.paragraphs])
        # Simulate pages as 3000-char chunks for docx
        pages = [text[i:i+3000] for i in range(0, len(text), 3000)]
        log.debug(f"[preprocess] DOCX pseudo-pages={len(pages)}")
        return pages
    else:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        pages = [text[i:i+3000] for i in range(0, len(text), 3000)]
        log.debug(f"[preprocess] TXT pseudo-pages={len(pages)}")
        return pages


def standard_pre_chunks(pages: List[str], max_tokens: int = 4000, overlap_tokens: int = 400) -> List[Dict[str, Any]]:
    """Return coarse-grained chunks prior to header detection."""
    text = "\n".join(pages)
    max_chars = max_tokens * APPROX_CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * APPROX_CHARS_PER_TOKEN
    chunks: List[Dict[str, Any]] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunk_text = text[start:end]
        if end < len(text):
            nl = text.rfind("\n", start, end)
            if nl != -1 and nl > start + 200:
                chunk_text = text[start:nl]
                end = nl
        chunks.append({
            "document": "Uploaded Document",
            "section_number": "",
            "section_name": "Pre-chunk",
            "text": chunk_text.strip(),
            "meta": {"approx_start": start, "approx_end": end}
        })
        if end >= len(text):
            break
        start = max(0, end - overlap_chars)
    log.debug(f"[preprocess] standard pre-chunks={len(chunks)}")
    return chunks


def _chunk_text_for_headers(pages: List[str], max_tokens: int = 120_000) -> Iterable[Dict[str, Any]]:
    """Yield chunks (joined pages) capped to the token budget for header detection."""
    if not pages:
        return []
    chunks: List[Dict[str, Any]] = []
    current_pages: List[str] = []
    start_page = 0
    for idx, page in enumerate(pages):
        candidate_pages = current_pages + [page]
        candidate_text = "\n".join(candidate_pages)
        candidate_tokens = approximate_tokens(candidate_text)
        if current_pages and candidate_tokens > max_tokens:
            chunks.append({
                "start_page": start_page,
                "end_page": start_page + len(current_pages) - 1,
                "text": "\n".join(current_pages)
            })
            current_pages = [page]
            start_page = idx
        else:
            current_pages = candidate_pages
    if current_pages:
        chunks.append({
            "start_page": start_page,
            "end_page": start_page + len(current_pages) - 1,
            "text": "\n".join(current_pages)
        })
    log.debug(f"[preprocess] header LLM chunks={len(chunks)}")
    return chunks


def _initial_header_spans(pages: List[str]):
    """First pass: use regex to locate section headings and spans."""
    headers = []
    for pi, page in enumerate(pages):
        for li, line in enumerate(page.splitlines()):
            m = HEADER_RX.match(line) or ALT_HEADER_RX.match(line)
            if m:
                num = m.group(1)
                name = m.group(2).strip()
                headers.append({"page": pi, "line": li, "section_number": num, "section_name": name})
    log.debug(f"[preprocess] detected headers via regex = {len(headers)}")
    return headers


def _locate_heading_in_pages(pages: List[str], section_number: str, section_name: str, start_page: int, end_page: int) -> Optional[Tuple[int, int]]:
    search_patterns = [
        rf"\b{re.escape(section_number)}\b\s*[-:.]?\s*{re.escape(section_name)}",
        rf"Section\s+{re.escape(section_number)}\s*[-:.]?\s*{re.escape(section_name)}",
        rf"{re.escape(section_number)}\s+{re.escape(section_name)}"
    ]
    compiled = [re.compile(pat, re.IGNORECASE) for pat in search_patterns]
    for pi in range(start_page, min(end_page + 1, len(pages))):
        lines = pages[pi].splitlines()
        for li, line in enumerate(lines):
            for rx in compiled:
                if rx.search(line.strip()):
                    return pi, li
    return None


async def detect_headers_and_sections_async(pages: List[str], client, model: str) -> List[Dict[str, Any]]:
    """Combine regex + LLM detected headers and return section chunks."""
    regex_headers = _initial_header_spans(pages)

    from ..prompts import HEADER_DETECTION_SYSTEM

    llm_headers: List[Dict[str, Any]] = []
    header_chunks = list(_chunk_text_for_headers(pages))
    if header_chunks:
        tasks = []
        for chunk in header_chunks:
            user = (
                "You are given an excerpt from a technical document. "
                "Identify every numbered section or subsection heading present. "
                "Return JSON array [{\"section_number\":\"\", \"section_name\":\"\"}] with no prose.\n\nTEXT:\n"
                + chunk["text"]
            )
            tasks.append(client.acomplete(model=model, system=HEADER_DETECTION_SYSTEM, user=user, temperature=0.0, max_tokens=800))

        responses = await asyncio.gather(*tasks, return_exceptions=True)
        for chunk, resp in zip(header_chunks, responses):
            if isinstance(resp, Exception):
                log.error("[preprocess] header LLM chunk %s failed: %s", chunk["start_page"], resp)
                continue
            try:
                data = json.loads(resp)
            except json.JSONDecodeError:
                log.error("[preprocess] header LLM response not JSON: %s", resp)
                continue
            for item in data:
                if not isinstance(item, dict):
                    continue
                section_number = str(item.get("section_number", "")).strip()
                section_name = str(item.get("section_name", "")).strip()
                if not section_number or not section_name:
                    continue
                loc = _locate_heading_in_pages(pages, section_number, section_name, chunk["start_page"], chunk["end_page"])
                if loc is None:
                    log.debug("[preprocess] unable to localize heading %s %s", section_number, section_name)
                    continue
                llm_headers.append({
                    "page": loc[0],
                    "line": loc[1],
                    "section_number": section_number,
                    "section_name": section_name
                })

    combined = {(h["page"], h["line"], h["section_number"], h["section_name"]): h for h in regex_headers}
    for h in llm_headers:
        combined[(h["page"], h["line"], h["section_number"], h["section_name"])] = h

    headers = sorted(combined.values(), key=lambda h: (h["page"], h["line"]))
    chunks: List[Dict[str, Any]] = []
    for i, h in enumerate(headers):
        start_page = h["page"]
        start_line = h["line"]
        end_page = headers[i + 1]["page"] if i + 1 < len(headers) else len(pages) - 1
        seg_lines: List[str] = []
        for pi in range(start_page, end_page + 1):
            lines = pages[pi].splitlines()
            start_idx = start_line if pi == start_page else 0
            seg_lines.extend(lines[start_idx:])
        text = "\n".join(seg_lines).strip()
        if not text:
            continue
        chunks.append({
            "document": "Uploaded Document",
            "section_number": h["section_number"],
            "section_name": h["section_name"],
            "text": text,
            "meta": {"start_page": start_page, "end_page": end_page}
        })
    if not chunks:
        all_text = "\n".join(pages)
        chunks = [{
            "document": "Uploaded Document",
            "section_number": "",
            "section_name": "Body",
            "text": all_text,
            "meta": {"start_page": 0, "end_page": len(pages) - 1}
        }]
    log.debug(f"[preprocess] sections={len(chunks)} (regex={len(regex_headers)} llm={len(llm_headers)})")
    return chunks
