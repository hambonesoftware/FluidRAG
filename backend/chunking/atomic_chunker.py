"""Atomic clause-level chunker for standards documents."""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

_WORD_RE = re.compile(r"\w+")
_CLAUSE_RE = re.compile(
    r"(?m)^(?P<num>(?:\d+\.)*\d+)(?:\s+(?P<head>[^\n]+))?"
)
_BULLET_RE = re.compile(r"(?m)^(?:\(|\[)?(?P<label>[a-zA-Z]{1,2})(?:\)|\])\s+")
_SEMICOLON_SPLIT_RE = re.compile(
    r";\s+(?=(?:[A-Za-z][^;\n]+\b(?:shall|must|should|may)\b)|(?:each|the|it|they)\b)",
    re.I,
)
_MUST_RE = re.compile(r"\b(shall|must|shall not)\b", re.I)
_MAY_RE = re.compile(r"\b(should|may)\b", re.I)
_NUMBER_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)")
_UNIT_RE = re.compile(
    r"\b(?:mm|cm|m|km|in|inch|ft|hz|khz|mhz|°c|°f|psi|bar|nm|n|nm|kw|ma|v|amp|a|db\(a\))\b",
    re.I,
)
_REF_RE = re.compile(
    r"\b(?:in accordance with|per\s+[A-Z][A-Z0-9\-: ]+|as specified in\s+(?:Annex|Appendix))",
    re.I,
)
_APPENDIX_RE = re.compile(r"(?i)\b(annex|appendix)\s*([A-Z])(\d+)?\b")


def _approx_tokens(text: str) -> int:
    words = _WORD_RE.findall(text)
    return max(1, int(math.ceil(len(words) * 1.3)))


@dataclass
class MicroChunkConfig:
    target_tokens: int = 180
    min_tokens: int = 40
    max_tokens: int = 320
    one_requirement_per_chunk: bool = True
    copy_leadin_to_prefix: bool = True
    prepend_prefix_in_embedding: bool = True


class AtomicChunker:
    """Split standards text into atomic micro-chunks."""

    def __init__(self, config: Optional[MicroChunkConfig | Dict[str, Any]] = None) -> None:
        if isinstance(config, dict):
            self.config = MicroChunkConfig(**config)
        else:
            self.config = config or MicroChunkConfig()

    # public API
    def chunk(
        self,
        doc_id: str,
        pages: Sequence[Dict[str, Any]],
        header_spans: Sequence[Dict[str, Any]] | None = None,
    ) -> List[Dict[str, Any]]:
        text, page_ranges = self._stitch_pages(pages)
        clause_spans = list(self._find_clause_spans(text))
        if not clause_spans:
            clause_spans = [(0, len(text), None, None)]
        resolved_headers = self._resolve_headers(header_spans or [])
        chunks: List[Dict[str, Any]] = []
        for idx, (start, end, clause_id, heading) in enumerate(clause_spans):
            clause_text = text[start:end].strip()
            clause_id = clause_id or self._infer_clause_id(clause_text)
            heading = heading or resolved_headers.get(clause_id or "", heading)
            clause_body = self._strip_heading_from_body(clause_text, clause_id, heading)
            page_span = self._page_span(start, end, page_ranges)
            for sub_idx, requirement in enumerate(
                self._yield_requirements(clause_body, clause_id)
            ):
                if not requirement.text:
                    continue
                chunk_id = f"{doc_id}|{clause_id or 'clause'}|{idx:03d}|{sub_idx:02d}"
                hier = self._build_hierarchy(clause_id, heading, resolved_headers)
                prefix = self._build_prefix(doc_id, clause_id, heading, requirement.leadin)
                chunk = {
                    "id": chunk_id,
                    "doc_id": doc_id,
                    "hier": hier,
                    "prefix": prefix,
                    "text": requirement.text,
                    "page_span": list(page_span),
                    "tokens": _approx_tokens(requirement.text),
                    "signals": self._compute_signals(requirement.text),
                }
                chunks.append(chunk)
        return chunks

    def _stitch_pages(
        self, pages: Sequence[Dict[str, Any]]
    ) -> Tuple[str, List[Tuple[int, int, int]]]:
        combined: List[str] = []
        ranges: List[Tuple[int, int, int]] = []
        cursor = 0
        for page in pages:
            page_no = int(page.get("page") or page.get("page_number") or len(ranges) + 1)
            text = str(page.get("text") or "")
            combined.append(text)
            start = cursor
            cursor += len(text)
            ranges.append((start, cursor, page_no))
        return "\n".join(combined), ranges

    def _find_clause_spans(
        self, text: str
    ) -> Iterator[Tuple[int, int, Optional[str], Optional[str]]]:
        matches = list(_CLAUSE_RE.finditer(text))
        for idx, match in enumerate(matches):
            start = match.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            clause_id = match.group("num")
            heading = (match.group("head") or "").strip() or None
            yield start, end, clause_id, heading

    def _infer_clause_id(self, text: str) -> Optional[str]:
        match = _CLAUSE_RE.match(text)
        if match:
            return match.group("num")
        return None

    def _strip_heading_from_body(
        self, clause_text: str, clause_id: Optional[str], heading: Optional[str]
    ) -> str:
        body = clause_text
        if clause_id:
            body = re.sub(rf"^(?:{re.escape(clause_id)})(?:\s+{re.escape(heading or '')})?", "", body, count=1).strip()
        return body

    def _yield_requirements(
        self, text: str, clause_id: Optional[str]
    ) -> Iterator["RequirementSegment"]:
        bullets = list(_BULLET_RE.finditer(text))
        if bullets:
            leadin = text[: bullets[0].start()].strip()
            for idx, match in enumerate(bullets):
                start = match.end()
                end = bullets[idx + 1].start() if idx + 1 < len(bullets) else len(text)
                body = text[start:end].strip()
                body_segments = self._split_semicolons(body)
                for seg_idx, segment in enumerate(body_segments):
                    yield RequirementSegment(segment, leadin if seg_idx == 0 else None)
            return
        for segment in self._split_semicolons(text):
            yield RequirementSegment(segment, None)

    def _split_semicolons(self, text: str) -> List[str]:
        parts = _SEMICOLON_SPLIT_RE.split(text)
        cleaned = [part.strip().strip(";").strip() for part in parts if part.strip()]
        if not cleaned:
            return [text.strip()]
        return cleaned

    def _page_span(
        self, start: int, end: int, ranges: Sequence[Tuple[int, int, int]]
    ) -> Tuple[int, int]:
        start_page = end_page = ranges[-1][2] if ranges else 1
        for begin, finish, page_no in ranges:
            if begin <= start < finish:
                start_page = page_no
            if begin < end <= finish:
                end_page = page_no
        return start_page, end_page

    def _build_hierarchy(
        self,
        clause_id: Optional[str],
        heading: Optional[str],
        headers: Dict[str, str],
    ) -> Dict[str, Optional[str]]:
        section = subsection = clause = None
        if clause_id:
            parts = clause_id.split(".")
            if parts:
                section = parts[0]
            if len(parts) > 1:
                subsection = ".".join(parts[:2])
            if len(parts) > 2:
                clause = ".".join(parts[:3])
            else:
                clause = clause_id
        part = None
        for key, value in headers.items():
            if key.upper().startswith("ANNEX") or key.upper().startswith("APPENDIX"):
                match = _APPENDIX_RE.search(key)
                if match:
                    part = match.group(2)
        return {
            "part": part,
            "section": section,
            "subsection": subsection,
            "clause": clause,
            "heading": heading,
        }

    def _build_prefix(
        self,
        doc_id: str,
        clause_id: Optional[str],
        heading: Optional[str],
        leadin: Optional[str],
    ) -> str:
        prefix = f"{doc_id}"
        if clause_id:
            prefix += f" §{clause_id}"
        if heading:
            prefix += f" — {heading}"
        prefix += ": "
        if leadin and self.config.copy_leadin_to_prefix:
            prefix += leadin.strip() + " "
        return prefix

    def _compute_signals(self, text: str) -> Dict[str, Any]:
        numerics = len(_NUMBER_RE.findall(text))
        units = len(_UNIT_RE.findall(text))
        must_shall = len(_MUST_RE.findall(text))
        may_should = len(_MAY_RE.findall(text))
        refs = len(_REF_RE.findall(text))
        tokens = [token.lower() for token in _WORD_RE.findall(text)]
        counts = {token: tokens.count(token) for token in set(tokens)}
        total = len(tokens) or 1
        entropy = 0.0
        for count in counts.values():
            p = count / total
            entropy -= p * math.log(max(p, 1e-6))
        entropy = entropy / math.log(total + 1)
        list_score = 1 if "\n" in text or any(token.endswith(")") for token in tokens) else 0
        return {
            "numerics": numerics,
            "units": units,
            "must_shall": must_shall,
            "may_should": may_should,
            "list": list_score,
            "refs": refs,
            "entropy": entropy,
        }

    def _resolve_headers(self, headers: Sequence[Dict[str, Any]]) -> Dict[str, str]:
        resolved: Dict[str, str] = {}
        for header in headers:
            clause_id = str(header.get("clause") or header.get("section") or "").strip()
            text = str(header.get("text") or header.get("heading") or "").strip()
            if clause_id and text:
                resolved[clause_id] = text
        return resolved


class RequirementSegment:
    __slots__ = ("text", "leadin")

    def __init__(self, text: str, leadin: Optional[str]) -> None:
        self.text = text.strip()
        self.leadin = leadin


__all__ = ["AtomicChunker", "MicroChunkConfig"]
