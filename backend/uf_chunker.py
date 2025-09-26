from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


HEADER_PATTERN = re.compile(
    r"""
    ^
    (?:
        (?P<numeric_section>\d+\))
        |
        (?P<appendix_top>(?:Appendix|Annex)\s+[A-Z])
        |
        (?P<appendix_sub_AN>[A-Z]\d{1,3}\.)
        |
        (?P<appendix_sub_AlN>[A-Z]\.\d{1,3})
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
MODAL_WORDS = {"may", "shall", "should", "must", "will", "can", "could", "would"}
DOMAIN_KEYWORDS = {
    "safety": {"safety", "safe", "hazard"},
    "performance": {"performance", "efficiency", "output"},
    "utilities": {"utility", "utilities", "consumption", "power"},
    "financial": {"cost", "budget", "finance"},
    "compliance": {"compliance", "regulation", "standard"},
}


@dataclass
class UFChunk:
    """Container for an Ultrafine chunk."""

    id: str
    page: int
    span_char: Tuple[int, int]
    span_bbox: Optional[Tuple[float, float, float, float]]
    text: str
    style: Dict[str, Any]
    lex: Dict[str, Any]
    emb: List[float]
    domain_hint: Optional[str] = None
    entropy: Dict[str, float] = field(default_factory=dict)
    header_anchor: bool = False

    def preview(self, max_len: int = 80) -> str:
        text = self.text.strip().replace("\n", " ")
        return text[:max_len] + ("…" if len(text) > max_len else "")


def _hash_token(token: str) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def _embed_text(text: str, dims: int = 8) -> List[float]:
    tokens = re.findall(r"[\w%]+", text.lower()) or [""]
    vec = [0.0] * dims
    for tok in tokens:
        h = _hash_token(tok)
        for i in range(dims):
            vec[i] += ((h >> (i * 4)) & 0xF) / 15.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _extract_numbers(tokens: Sequence[str]) -> List[str]:
    results: List[str] = []
    for tok in tokens:
        if re.search(r"\d", tok):
            results.append(tok)
    return results


def _extract_units(tokens: Sequence[str]) -> List[str]:
    units_pattern = re.compile(r"(?:%|kV|kVA|MW|kW|Hz|°C|°F|psi)", re.IGNORECASE)
    return [tok for tok in tokens if units_pattern.search(tok)]


def _has_modal(tokens: Sequence[str]) -> bool:
    return any(tok.lower() in MODAL_WORDS for tok in tokens)


def _compute_indent(token: Dict[str, Any]) -> float:
    return float(token.get("indent", 0.0) or 0.0)


def _infer_domain_hint(text: str) -> Optional[str]:
    lowered = text.lower()
    best_hint: Optional[str] = None
    best_hits = 0
    for hint, keywords in DOMAIN_KEYWORDS.items():
        hits = sum(1 for keyword in keywords if keyword in lowered)
        if hits > best_hits:
            best_hits = hits
            best_hint = hint
    return best_hint if best_hits else None


def _bbox_union(tokens: Sequence[Dict[str, Any]]) -> Optional[Tuple[float, float, float, float]]:
    bboxes = [tok.get("bbox") for tok in tokens if tok.get("bbox")]
    if not bboxes:
        return None
    x0 = min(box[0] for box in bboxes)
    y0 = min(box[1] for box in bboxes)
    x1 = max(box[2] for box in bboxes)
    y1 = max(box[3] for box in bboxes)
    return float(x0), float(y0), float(x1), float(y1)


def uf_chunk(doc_decomp: Dict[str, Any], max_tokens: int = 90, overlap: int = 12) -> List[UFChunk]:
    """Chunk a decomposed document into Ultrafine chunks."""

    pages: List[Dict[str, Any]] = doc_decomp.get("pages", [])
    chunks: List[UFChunk] = []
    chunk_index = 0

    for page_idx, page in enumerate(pages):
        tokens: List[Dict[str, Any]] = page.get("tokens", [])
        if not tokens:
            continue
        i = 0
        while i < len(tokens):
            start_idx = i
            span_start = tokens[start_idx].get("start", 0)
            j = start_idx
            while j < len(tokens) and (j - start_idx) < max_tokens:
                if j > start_idx:
                    token_text = tokens[j]["text"].strip()
                    prev_text = tokens[j - 1]["text"].strip()
                    if HEADER_PATTERN.match(token_text):
                        break
                    if prev_text.endswith(".") and token_text[:1].isupper():
                        break
                    indent_delta = _compute_indent(tokens[j]) - _compute_indent(tokens[j - 1])
                    if indent_delta >= 2.0:
                        break
                j += 1
            if j == start_idx:
                j += 1
            chunk_tokens = tokens[start_idx:j]
            span_end = chunk_tokens[-1].get("end", span_start)
            text = page.get("text", "")[span_start:span_end]
            if not text:
                text = "".join(tok.get("text", "") for tok in chunk_tokens)
            raw_tokens = [tok.get("text", "") for tok in chunk_tokens]
            lex_numbers = _extract_numbers(raw_tokens)
            lex_units = _extract_units(raw_tokens)
            lex_has_modal = _has_modal(raw_tokens)
            style = {
                "font_size": float(chunk_tokens[0].get("font_size", 0.0) or 0.0),
                "bold": bool(chunk_tokens[0].get("bold", False)),
                "indent": float(chunk_tokens[0].get("indent", 0.0) or 0.0),
            }
            lex = {
                "has_modal": lex_has_modal,
                "numbers": lex_numbers,
                "units": lex_units,
                "citation_hints": bool(re.search(r"\[[^\]]+\]|\([^)]*\d{4}[^)]*\)", text)),
            }
            emb = _embed_text(text)
            chunk_id = f"uf_{page_idx + 1:04d}_{chunk_index:05d}"
            header_anchor = bool(HEADER_PATTERN.search(text.strip().splitlines()[0] if text.strip() else ""))
            bbox = _bbox_union(chunk_tokens)
            chunk = UFChunk(
                id=chunk_id,
                page=page_idx + 1,
                span_char=(int(span_start), int(span_end)),
                span_bbox=bbox,
                text=text,
                style=style,
                lex=lex,
                emb=emb,
                domain_hint=_infer_domain_hint(text),
                header_anchor=header_anchor,
            )
            chunks.append(chunk)
            chunk_index += 1
            if j >= len(tokens):
                break
            i = max(j - max(overlap, 0), start_idx + 1)

    return chunks


__all__ = ["UFChunk", "uf_chunk"]
