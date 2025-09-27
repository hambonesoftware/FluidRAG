"""Helpers for consolidating preprocess headers into final outputs."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional


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


def _extract_preprocess_payload(doc: object) -> object:
    """Return the raw preprocess headers payload from ``doc``."""

    preprocess = getattr(doc, "preprocess", None)
    if preprocess is not None:
        for attr in ("headers_by_page", "headers"):
            payload = getattr(preprocess, attr, None)
            if payload:
                return payload

    for attr in ("decomp", "payload", "data"):
        candidate = getattr(doc, attr, None)
        if isinstance(candidate, Mapping):
            payload = _extract_preprocess_payload(candidate)
            if payload:
                return payload

    if isinstance(doc, Mapping):
        preprocess = doc.get("preprocess")
        if isinstance(preprocess, Mapping):
            for key in ("headers_by_page", "headers", "pages"):
                payload = preprocess.get(key)
                if payload:
                    return payload
        for key in ("preprocess_headers", "headers", "headers_by_page", "header_pages"):
            payload = doc.get(key)
            if payload:
                return payload

    return []


def _to_int(value: object) -> Optional[int]:
    """Return ``value`` coerced to ``int`` when possible."""

    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive guard
        return None


def _normalize_headers(doc: object) -> list[dict[str, object]]:
    headers_payload: Any = _extract_preprocess_payload(doc)

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
        line_idx = _to_int(entry.get("line_idx"))
        normalized.append(
            {
                "page": page_num,
                "line_idx": line_idx,
                "text": text,
                "bold": entry.get("bold"),
                "font_pt": entry.get("font_pt"),
                "bbox": entry.get("bbox"),
            }
        )
    return normalized


def finalize_headers_preprocess_only(doc: object) -> list[dict[str, object]]:
    """Use preprocess headers as the single source of truth for final headers.

    The resulting list is considered canonical when ``HEADER_MODE`` is set to
    ``"preprocess_only"``. Downstream systems should consume either the
    returned list or the persisted ``headers_final.json`` artifact and must not
    expect EFHG scoring, audits, or suppression heuristics to have been
    applied.
    """

    raw_entries = _normalize_headers(doc)

    seen: set[tuple[int, object, str]] = set()
    final: list[dict[str, object]] = []
    for header in raw_entries:
        page = header.get("page")
        line_idx = _to_int(header.get("line_idx"))
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

