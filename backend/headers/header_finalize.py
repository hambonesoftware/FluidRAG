"""Helpers for consolidating preprocess headers into final outputs."""

from __future__ import annotations

from typing import Iterable, Mapping


def _iter_header_dicts(payload: object) -> Iterable[Mapping[str, object]]:
    """Yield header dictionaries from the preprocess payload.

    ``headers_by_page`` historically appeared either as a flattened sequence of
    header dictionaries or as a sequence of page blocks containing ``headers``.
    The new preprocess-only mode expects a flat list, but we keep this helper to
    gracefully support both representations while the pipeline transitions.
    """

    if isinstance(payload, Mapping):
        headers = payload.get("headers")
        if isinstance(headers, Iterable):
            for entry in headers:
                if isinstance(entry, Mapping):
                    yield from _iter_header_dicts(entry)
            return
    if isinstance(payload, Iterable):
        for item in payload:
            if isinstance(item, Mapping) and "headers" in item:
                yield from _iter_header_dicts(item["headers"])
            elif isinstance(item, Mapping):
                yield item


def _normalize_headers(doc: object) -> list[dict[str, object]]:
    preprocess = getattr(doc, "preprocess", None)
    headers_payload = None
    if preprocess is not None:
        headers_payload = getattr(preprocess, "headers_by_page", None)
        if headers_payload is None:
            headers_payload = getattr(preprocess, "headers", None)
    if headers_payload is None and isinstance(doc, Mapping):
        preprocess = doc.get("preprocess") if isinstance(doc, Mapping) else None
        if isinstance(preprocess, Mapping):
            headers_payload = (
                preprocess.get("headers_by_page")
                or preprocess.get("headers")
                or preprocess.get("pages")
            )
    if headers_payload is None:
        headers_payload = []

    normalized: list[dict[str, object]] = []
    for entry in _iter_header_dicts(headers_payload):
        page = entry.get("page")
        try:
            page_num = int(page)
        except Exception:  # pragma: no cover - defensive
            continue
        text = str(entry.get("text") or entry.get("name") or "").strip()
        if not text:
            continue
        normalized.append(
            {
                "page": page_num,
                "line_idx": entry.get("line_idx"),
                "text": text,
                "bold": entry.get("bold"),
                "font_pt": entry.get("font_pt"),
                "bbox": entry.get("bbox"),
            }
        )
    return normalized


def finalize_headers_preprocess_only(doc: object) -> list[dict[str, object]]:
    """Use preprocess headers as the single source of truth for final headers."""

    raw_entries = _normalize_headers(doc)

    seen: set[tuple[int, object, str]] = set()
    final: list[dict[str, object]] = []
    for header in raw_entries:
        page = header.get("page")
        line_idx = header.get("line_idx")
        text = str(header.get("text", "")).strip()
        key = (int(page), line_idx, text)
        if key in seen:
            continue
        seen.add(key)
        final.append(
            {
                "page": int(page),
                "line_idx": line_idx,
                "text": text,
                "bold": header.get("bold"),
                "font_pt": header.get("font_pt"),
                "bbox": header.get("bbox"),
                "provenance": "preprocess",
            }
        )

    final.sort(key=lambda item: (item["page"], item["line_idx"] if item["line_idx"] is not None else 1_000_000))

    artifacts = getattr(doc, "artifacts", None)
    if artifacts is not None:
        try:
            artifacts.write_json(
                "headers_final.json",
                {"headers_final": final},
            )
        except Exception:  # pragma: no cover - defensive
            pass
        try:
            lines = ["page\tline_idx\ttext"] + [
                f"{item['page']}\t{item['line_idx']}\t{item['text']}" for item in final
            ]
            artifacts.write_text("headers_final.tsv", "\n".join(lines))
        except Exception:  # pragma: no cover - defensive
            pass

    return final


__all__ = ["finalize_headers_preprocess_only"]

