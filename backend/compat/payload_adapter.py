"""Adapter that converts the new context buckets into the legacy message payload."""
from __future__ import annotations

from typing import Dict, Iterable, List

from ..retrieval.utils import trim_context_snippets


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


def _apply_context_budget(
    context_buckets: Dict[str, List[Dict[str, object]]]
) -> Dict[str, List[Dict[str, object]]]:
    ordered: List[tuple[str, Dict[str, object]]] = []
    for bucket_name in ("Standards", "ProjectSpec", "Risk"):
        for entry in context_buckets.get(bucket_name, []):
            ordered.append((bucket_name, dict(entry)))
    trimmed_texts = trim_context_snippets([entry.get("text", "") for _, entry in ordered])
    trimmed_buckets: Dict[str, List[Dict[str, object]]] = {
        key: [] for key in context_buckets
    }
    trimmed_buckets.setdefault("Standards", [])
    trimmed_buckets.setdefault("ProjectSpec", [])
    trimmed_buckets.setdefault("Risk", [])
    for bucket_name, entries in context_buckets.items():
        if bucket_name not in {"Standards", "ProjectSpec", "Risk"}:
            trimmed_buckets[bucket_name] = [dict(entry) for entry in entries]
    for (bucket_name, entry), text in zip(ordered, trimmed_texts):
        new_entry = dict(entry)
        new_entry["text"] = text
        trimmed_buckets[bucket_name].append(new_entry)
    return trimmed_buckets


def to_legacy_llm_message(context_buckets: Dict[str, List[Dict[str, object]]], question: str) -> Dict[str, object]:
    trimmed = _apply_context_budget(context_buckets)
    standards = trimmed.get("Standards", [])
    project = trimmed.get("ProjectSpec", [])
    risk = trimmed.get("Risk", [])
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
