"""Macro chunk builder aggregating atomic micro-chunks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .atomic_chunker import _approx_tokens


@dataclass
class MacroChunkConfig:
    target_tokens: int = 1600
    max_tokens: int = 2200


class MacroChunker:
    """Construct macro chunks by rolling up micro chunks within a hierarchy."""

    def __init__(self, config: Optional[MacroChunkConfig | Dict[str, Any]] = None) -> None:
        if isinstance(config, dict):
            self.config = MacroChunkConfig(**config)
        else:
            self.config = config or MacroChunkConfig()

    def _ordered_unique(self, values: Iterable[Optional[str]]) -> List[str]:
        seen: set[str] = set()
        ordered: List[str] = []
        for value in values:
            if not value:
                continue
            if value in seen:
                continue
            seen.add(value)
            ordered.append(str(value))
        return ordered

    def build(self, micro_chunks: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ordered = sorted(
            micro_chunks,
            key=lambda chunk: (
                int((chunk.get("page_span") or [0])[0]),
                str((chunk.get("hier") or {}).get("clause") or chunk.get("id")),
            ),
        )
        groups: Dict[Tuple[str, Optional[str], Optional[str]], List[Dict[str, Any]]] = {}
        for chunk in ordered:
            doc_id = str(chunk.get("doc_id"))
            hier = chunk.get("hier") or {}
            section = hier.get("section")
            subsection = hier.get("subsection")
            key = (doc_id, section, subsection)
            groups.setdefault(key, []).append(chunk)
        macros: List[Dict[str, Any]] = []
        for (doc_id, section, subsection), members in groups.items():
            if not members:
                continue
            text_parts = [m.get("text", "") for m in members]
            joined_text = "\n\n".join(part for part in text_parts if part)
            token_estimate = _approx_tokens(joined_text)
            page_start = min(int(m.get("page_span", [1, 1])[0]) for m in members)
            page_end = max(int(m.get("page_span", [1, 1])[1]) for m in members)
            hier_path = " → ".join(
                [part for part in (section, subsection) if part]
            ) or (section or subsection or "root")
            clause_values = self._ordered_unique(
                (m.get("hier") or {}).get("clause") for m in members
            )
            heading_values = self._ordered_unique(
                (m.get("hier") or {}).get("heading") for m in members
            )
            part_values = self._ordered_unique(
                (m.get("hier") or {}).get("part") for m in members
            )
            section_ids = self._ordered_unique(m.get("section_id") for m in members)
            section_titles = self._ordered_unique(
                m.get("section_title") or (m.get("hier") or {}).get("heading")
                for m in members
            )
            pages = sorted({
                p
                for m in members
                for p in (m.get("pages") or [])
                if isinstance(p, int)
            })
            if not pages:
                pages = list(range(page_start, page_end + 1))
            micro_token_counts = [int(m.get("tokens") or m.get("token_count") or 0) for m in members]
            micro_char_counts = [len(m.get("text", "")) for m in members]
            macro_index = len(macros)
            macro_id = f"{doc_id}|macro|{section or '0'}|{subsection or '0'}|{len(macros):03d}"
            macros.append(
                {
                    "macro_id": macro_id,
                    "doc_id": doc_id,
                    "hier_path": hier_path,
                    "text": joined_text,
                    "page_span": [page_start, page_end],
                    "tokens": token_estimate,
                    "micro_children": [m.get("id") for m in members],
                    "micro_count": len(members),
                    "micro_token_total": sum(micro_token_counts),
                    "micro_token_avg": (
                        sum(micro_token_counts) / len(members)
                        if members
                        else 0.0
                    ),
                    "micro_token_min": min(micro_token_counts) if micro_token_counts else 0,
                    "micro_token_max": max(micro_token_counts) if micro_token_counts else 0,
                    "char_count": len(joined_text),
                    "micro_char_total": sum(micro_char_counts),
                    "pages": pages,
                    "hierarchy": {
                        "part": part_values[0] if part_values else None,
                        "parts": part_values,
                        "section": section,
                        "section_ids": section_ids,
                        "section_titles": section_titles,
                        "subsection": subsection,
                        "headings": heading_values,
                        "clauses": clause_values,
                    },
                    "section_id": section_ids[0] if section_ids else None,
                    "section_title": section_titles[0] if section_titles else None,
                    "heading": heading_values[0] if heading_values else None,
                    "macro_index": macro_index,
                    "resolution": "macro",
                }
            )
        return macros


__all__ = ["MacroChunker", "MacroChunkConfig"]
