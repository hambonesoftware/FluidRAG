"""Macro chunk builder aggregating atomic micro-chunks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
                }
            )
        return macros


__all__ = ["MacroChunker", "MacroChunkConfig"]
