"""Header-specific unicode normalization helpers."""
from __future__ import annotations

from typing import Iterable

# Additional Unicode whitespace characters frequently encountered in OCR dumps.
UNICODE_SPACES = {
    "\u00A0",
    "\u2000",
    "\u2001",
    "\u2002",
    "\u2003",
    "\u2004",
    "\u2005",
    "\u2006",
    "\u2007",
    "\u2008",
    "\u2009",
    "\u200A",
    "\u202F",
    "\u205F",
    "\u3000",
    "\u180E",
    "\u200B",
    "\u2060",
}

# Dot-like glyphs that should be normalized to a period before regexing.
DOT_VARIANTS = {"\u2024", "\u2027", "\uFF0E"}


def _iter_chars(text: str | None) -> Iterable[str]:
    if not text:
        return ()
    return text


def normalize_for_headers(text: str) -> str:
    """Return a whitespace/dot-normalised version of ``text`` for header checks."""

    if not text:
        return text

    out: list[str] = []
    for ch in _iter_chars(text):
        if ch in UNICODE_SPACES:
            out.append(" ")
        elif ch in DOT_VARIANTS:
            out.append(".")
        else:
            out.append(ch)

    normalized = "".join(out)
    # Collapse multi-space runs while preserving single spaces for downstream regexes.
    collapsed = " ".join(normalized.split())
    return collapsed


__all__ = ["DOT_VARIANTS", "UNICODE_SPACES", "normalize_for_headers"]

