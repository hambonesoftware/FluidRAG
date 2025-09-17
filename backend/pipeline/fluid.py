import logging
from typing import List, Dict, Any

log = logging.getLogger("FluidRAG.fluid")

MAX_WORDS = 1200   # ~1k-2k tokens
MIN_WORDS = 120

def _word_count(s: str) -> int:
    return len(s.split())

def fluid_refine_chunks(chunks: List[Dict[str, Any]]):
    """Merge short chunks and split very long ones with gentle overlap."""
    # Merge small
    merged = []
    buf = None
    for ch in chunks:
        if buf is None:
            buf = ch.copy()
            continue
        if _word_count(buf["text"]) < MIN_WORDS:
            buf["text"] = (buf["text"] + "\n\n" + ch["text"]).strip()
            buf["section_number"] = buf["section_number"] or ch["section_number"]
            buf["section_name"] = buf["section_name"] or ch["section_name"]
        else:
            merged.append(buf)
            buf = ch.copy()
    if buf:
        merged.append(buf)

    # Split long
    refined = []
    overlap = 80  # words
    for ch in merged:
        words = ch["text"].split()
        if len(words) <= MAX_WORDS:
            refined.append(ch)
            continue
        i = 0
        idx = 1
        while i < len(words):
            part = " ".join(words[i:i+MAX_WORDS])
            refined.append({
                "document": ch["document"],
                "section_number": ch["section_number"],
                "section_name": f'{ch["section_name"]} (part {idx})',
                "text": part,
                "meta": ch.get("meta", {})
            })
            i += MAX_WORDS - overlap
            idx += 1
    log.debug(f"[fluid] in={len(chunks)} merged={len(merged)} refined={len(refined)}")
    return refined
