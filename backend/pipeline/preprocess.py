import re
import logging
from typing import List, Dict, Any

from pypdf import PdfReader
from docx import Document

log = logging.getLogger("FluidRAG.preprocess")

HEADER_RX = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*(?:[-:]|\s+)\s*(.+?)\s*$")
ALT_HEADER_RX = re.compile(r"^\s*Section\s+(\d+(?:\.\d+)*)\s*[-:]?\s*(.+?)\s*$", re.IGNORECASE)

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

def detect_headers_and_sections(pages: List[str]):
    """Return chunks as dicts: document, section_number, section_name, text, meta."""
    heads = _initial_header_spans(pages)
    chunks = []
    for i, h in enumerate(heads):
        start_page = h["page"]
        start_line = h["line"]
        end_page = heads[i+1]["page"] if i+1 < len(heads) else len(pages)-1
        # gather text from start to next header
        seg_lines = []
        for pi in range(start_page, end_page + 1):
            lines = pages[pi].splitlines()
            s = start_line if pi == start_page else 0
            e = len(lines) if pi < end_page else len(lines)
            seg_lines.extend(lines[s:e])
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
    # Fallback: if no headers, treat full doc as one chunk
    if not chunks:
        all_text = "\n".join(pages)
        chunks = [{
            "document": "Uploaded Document",
            "section_number": "",
            "section_name": "Body",
            "text": all_text,
            "meta": {"start_page": 0, "end_page": len(pages)-1}
        }]
    log.debug(f"[preprocess] sections={len(chunks)}")
    return chunks
