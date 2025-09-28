"""Context window assembly for pass prompts."""

from __future__ import annotations

from typing import Any


def compose_window(ranked_chunks: list[dict[str, Any]], budget_tokens: int) -> str:
    """Assemble ordered, de-duped chunk window respecting token budget."""

    seen: set[str] = set()
    pieces: list[str] = []
    token_total = 0
    for chunk in ranked_chunks:
        chunk_id = str(chunk.get("chunk_id"))
        if not chunk_id or chunk_id in seen:
            continue
        text = str(chunk.get("text", "")).strip()
        if not text:
            continue
        tokens = len(text.split())
        if pieces and token_total + tokens > budget_tokens:
            break
        header = chunk.get("header_path") or chunk.get("header") or ""
        prefix = f"[{header}] " if header else ""
        pieces.append(prefix + text)
        seen.add(chunk_id)
        token_total += tokens
        if token_total >= budget_tokens:
            break
    return "\n\n".join(pieces)


__all__ = ["compose_window"]
