from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


HEADER_PATTERN = re.compile(r"^(?:\d+\)|A\d+\.)")
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
    """Representation of an Ultrafine (UF) chunk."""

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
    return [tok for tok in tokens if re.search(r"\d", tok)]


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


def _should_split(prev_token: Dict[str, Any], token: Dict[str, Any]) -> bool:
    token_text = token.get("text", "").strip()
    prev_text = prev_token.get("text", "").strip()
    if HEADER_PATTERN.match(token_text):
        return True
    if prev_text.endswith(".") and token_text[:1].isupper():
        return True
    indent_delta = _compute_indent(token) - _compute_indent(prev_token)
    return indent_delta >= 2.0


def _collect_text(page: Dict[str, Any], tokens: Sequence[Dict[str, Any]]) -> str:
    if not tokens:
        return ""
    start = int(tokens[0].get("start", 0))
    end = int(tokens[-1].get("end", start))
    page_text = page.get("text", "")
    if start < end <= len(page_text):
        text = page_text[start:end]
        if text.strip():
            return text
    return "".join(tok.get("text", "") for tok in tokens)


def _lexical_profile(text: str, tokens: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    raw_tokens = [tok.get("text", "") for tok in tokens]
    return {
        "has_modal": _has_modal(raw_tokens),
        "numbers": _extract_numbers(raw_tokens),
        "units": _extract_units(raw_tokens),
        "citation_hints": bool(re.search(r"\[[^\]]+\]|\([^)]*\d{4}[^)]*\)", text)),
    }


def _style_profile(tokens: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not tokens:
        return {"font_size": 0.0, "bold": False, "indent": 0.0}
    primary = tokens[0]
    return {
        "font_size": float(primary.get("font_size", 0.0) or 0.0),
        "bold": bool(primary.get("bold", False)),
        "indent": float(primary.get("indent", 0.0) or 0.0),
    }


def _header_anchor(text: str) -> bool:
    head = text.strip().splitlines()[0] if text.strip() else ""
    return bool(HEADER_PATTERN.match(head))


def _iter_segments(tokens: Sequence[Dict[str, Any]], max_tokens: int, overlap: int) -> Iterable[Tuple[int, int]]:
    start_idx = 0
    while start_idx < len(tokens):
        end_idx = min(len(tokens), start_idx + max_tokens)
        j = start_idx + 1
        while j < end_idx:
            if _should_split(tokens[j - 1], tokens[j]):
                end_idx = j
                break
            j += 1
        yield start_idx, end_idx
        if end_idx >= len(tokens):
            break
        step = max(1, max_tokens - max(0, overlap))
        # If we broke early due to header or indent, respect the boundary.
        if end_idx - start_idx < max_tokens:
            start_idx = end_idx
        else:
            start_idx = max(end_idx - step, start_idx + 1)


def uf_chunk(doc_decomp: Dict[str, Any], max_tokens: int = 90, overlap: int = 12) -> List[UFChunk]:
    """Chunk the normalized document decomposition using Ultrafine logic."""

    pages: List[Dict[str, Any]] = doc_decomp.get("pages", [])
    chunks: List[UFChunk] = []
    chunk_counter = 0

    for page_index, page in enumerate(pages):
        tokens: List[Dict[str, Any]] = page.get("tokens", [])
        if not tokens:
            continue
        segments = list(_iter_segments(tokens, max_tokens, overlap))
        for start_idx, end_idx in segments:
            segment_tokens = tokens[start_idx:end_idx]
            if not segment_tokens:
                continue
            text = _collect_text(page, segment_tokens)
            span_start = int(segment_tokens[0].get("start", 0))
            span_end = int(segment_tokens[-1].get("end", span_start))
            chunk = UFChunk(
                id=f"uf_{page_index + 1:04d}_{chunk_counter:05d}",
                page=page_index + 1,
                span_char=(span_start, span_end),
                span_bbox=_bbox_union(segment_tokens),
                text=text,
                style=_style_profile(segment_tokens),
                lex=_lexical_profile(text, segment_tokens),
                emb=_embed_text(text),
                domain_hint=_infer_domain_hint(text),
                header_anchor=_header_anchor(text),
            )
            chunks.append(chunk)
            chunk_counter += 1

    return chunks


__all__ = ["UFChunk", "uf_chunk", "HEADER_PATTERN"]
