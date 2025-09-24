"""Adapter that converts the new context buckets into the legacy message payload."""
from __future__ import annotations

from typing import Dict, Iterable, List


def _format_bucket(title: str, entries: Iterable[Dict[str, object]]) -> str:
    lines = [title]
    for entry in entries:
        chunk_id = entry.get("chunk_id", "")
        section = entry.get("section") or ""
        section_title = entry.get("section_title") or ""
        pages = entry.get("pages")
        prefix_parts = [part for part in [str(section).strip(), str(section_title).strip()] if part]
        prefix = " — ".join(prefix_parts) if prefix_parts else ""
        page_suffix = f" (pp. {pages[0]}-{pages[1]})" if isinstance(pages, (list, tuple)) else ""
        text = entry.get("text", "")
        lines.append(f"- {chunk_id}{': ' if prefix else ''}{prefix}{page_suffix}\n{text}".rstrip())
    return "\n".join(lines).strip()


def to_legacy_llm_message(context_buckets: Dict[str, List[Dict[str, object]]], question: str) -> Dict[str, object]:
    standards = context_buckets.get("Standards", [])
    project = context_buckets.get("ProjectSpec", [])
    risk = context_buckets.get("Risk", [])
    content_sections = [
        _format_bucket("[Standards]", standards),
        _format_bucket("[ProjectSpec]", project),
        _format_bucket("[Risk]", risk),
    ]
    user_content = "\n\n".join(filter(None, content_sections))
    return {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a technical standards extraction assistant. "
                    "Return the requested JSON exactly."
                ),
            },
            {
                "role": "user",
                "content": f"Question: {question}\n\n{user_content}".strip(),
            },
        ],
    }
