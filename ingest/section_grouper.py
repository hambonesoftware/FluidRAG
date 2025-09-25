"""Section helpers for grouping microchunks by detected headings."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple, TypedDict

from .microchunker import MicroChunk


class Section(TypedDict, total=False):
    doc_id: str
    section_id: str
    section_title: str
    header_anchor: Optional[str]
    char_start: Optional[int]
    char_end: Optional[int]
    page_start: Optional[int]
    page_end: Optional[int]


@dataclass
class _ChunkLike:
    section_id: str
    section_title: str
    header_anchor: Optional[str]
    text: str
    page_start: Optional[int]
    page_end: Optional[int]


def _iter_chunks(doc: Mapping[str, object]) -> Iterable[_ChunkLike]:
    chunks = doc.get("chunks")
    if isinstance(chunks, Mapping):
        chunks = chunks.get("items")
    if not isinstance(chunks, Sequence):
        return []
    results: List[_ChunkLike] = []
    for entry in chunks:
        if not isinstance(entry, Mapping):
            continue
        section_id = str(entry.get("section_id") or "").strip()
        section_title = str(entry.get("section_title") or "").strip()
        header_anchor = entry.get("header_anchor")
        text = str(entry.get("text") or "")
        page_start = entry.get("page_start")
        page_end = entry.get("page_end")
        results.append(
            _ChunkLike(
                section_id=section_id,
                section_title=section_title,
                header_anchor=header_anchor,
                text=text,
                page_start=int(page_start) if isinstance(page_start, (int, float)) else None,
                page_end=int(page_end) if isinstance(page_end, (int, float)) else None,
            )
        )
    return results


def build_sections(doc: Mapping[str, object]) -> List[Section]:
    """Build ordered section descriptors from a parsed document payload."""

    doc_id = str(doc.get("doc_id") or doc.get("document_id") or "doc-unknown")
    sections: List[Section] = []
    running = 0
    current: Optional[Section] = None

    for chunk in _iter_chunks(doc):
        text_length = len(chunk.text)
        section_id = chunk.section_id
        section_title = chunk.section_title

        if section_id and (current is None or current["section_id"] != section_id):
            if current is not None:
                current["char_end"] = running
                sections.append(current)
            current = Section(
                doc_id=doc_id,
                section_id=section_id,
                section_title=section_title or f"Section {section_id}",
                header_anchor=chunk.header_anchor,
                char_start=running,
                char_end=running + text_length,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
            )
        elif current is None and section_id:
            current = Section(
                doc_id=doc_id,
                section_id=section_id,
                section_title=section_title or f"Section {section_id}",
                header_anchor=chunk.header_anchor,
                char_start=running,
                char_end=running + text_length,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
            )
        elif current is not None:
            # Extend the current section window
            current["char_end"] = running + text_length
            if chunk.page_end:
                current["page_end"] = chunk.page_end
        running += text_length + 1  # Keep alignment with the microchunk concatenation

    if current is not None:
        current["char_end"] = running
        sections.append(current)

    return sections


def _section_by_char(sections: Sequence[Section], char_index: int) -> Optional[Section]:
    for section in sections:
        start = section.get("char_start")
        end = section.get("char_end")
        if start is None or end is None:
            continue
        if start <= char_index < end:
            return section
    return None


def _section_by_page(sections: Sequence[Section], page: Optional[int]) -> Optional[Section]:
    if page is None:
        return None
    for section in sections:
        start_page = section.get("page_start")
        end_page = section.get("page_end") or start_page
        if start_page is None:
            continue
        if start_page <= page <= (end_page or start_page):
            return section
    return None


def assign_micro_to_sections(
    micros: Sequence[MicroChunk],
    sections: Sequence[Section],
) -> Dict[str, List[str]]:
    """Assign microchunks to the nearest section definition."""

    mapping: Dict[str, List[str]] = {section["section_id"]: [] for section in sections if section.get("section_id")}

    for micro in micros:
        section_id = str(micro.get("section_id") or "").strip()
        target_section: Optional[Section] = None
        if section_id:
            target_section = next((s for s in sections if s.get("section_id") == section_id), None)
        if target_section is None and micro.get("char_span"):
            start_char = micro["char_span"][0]
            target_section = _section_by_char(sections, start_char)
        if target_section is None:
            target_section = _section_by_page(sections, micro.get("page"))
        if target_section is None and sections:
            target_section = sections[-1]
        if not target_section or not target_section.get("section_id"):
            continue
        mapping.setdefault(target_section["section_id"], []).append(micro["micro_id"])
    return mapping


__all__ = ["Section", "build_sections", "assign_micro_to_sections"]
