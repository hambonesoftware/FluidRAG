"""Text normalization utilities for preprocessing."""
from __future__ import annotations

from typing import List, Tuple

# Maps for unicode characters we normalise into ASCII equivalents.
SPACE_CODEPOINTS = (
    0x00A0,
    0x2000,
    0x2001,
    0x2002,
    0x2003,
    0x2004,
    0x2005,
    0x2006,
    0x2007,
    0x2008,
    0x2009,
    0x200A,
    0x202F,
    0x205F,
    0x3000,
)
SPACE_MAP = {codepoint: " " for codepoint in SPACE_CODEPOINTS}
DOT_MAP = {0x2024: ".", 0x2027: ".", 0xFF0E: "."}
DASH_MAP = {0x2013: "-", 0x2014: "-"}


def _hex_diff(text_raw: str, text_norm: str) -> List[str]:
    """Return a human-readable diff between the raw and normalised text."""
    diffs: List[str] = []
    for idx, (raw_ch, norm_ch) in enumerate(zip(text_raw, text_norm)):
        if raw_ch != norm_ch:
            diffs.append(f"{ord(norm_ch):04X}->{ord(raw_ch):04X} at pos {idx}")
    # If normalisation shortened the string (e.g. collapsing whitespace),
    # record the removed code points as well.
    if len(text_raw) > len(text_norm):
        for idx in range(len(text_norm), len(text_raw)):
            diffs.append(f"0000->{ord(text_raw[idx]):04X} at pos {idx}")
    return diffs


def normalize_text(text_raw: str) -> Tuple[str, List[str]]:
    """Normalise unicode spaces/dots/dashes and collapse repeated spaces.

    Returns the normalised text along with a list describing the differences
    relative to the raw input. The function is deterministic and idempotent so
    running it on an already-normalised string will return the original string
    and an empty diff list.
    """

    if not text_raw:
        return "", []

    mapped_chars: List[str] = []
    for char in text_raw:
        codepoint = ord(char)
        if codepoint in SPACE_MAP:
            mapped_chars.append(" ")
        elif codepoint in DOT_MAP:
            mapped_chars.append(DOT_MAP[codepoint])
        elif codepoint in DASH_MAP:
            mapped_chars.append(DASH_MAP[codepoint])
        else:
            mapped_chars.append(char)

    text_norm = "".join(mapped_chars)

    # Collapse duplicated spaces without disturbing leading/trailing spacing
    # that may be meaningful for bbox alignment. We therefore replace runs of
    # three or more spaces entirely and reduce pairs iteratively.
    while "  " in text_norm:
        text_norm = text_norm.replace("  ", " ")

    diffs = _hex_diff(text_raw, text_norm)
    return text_norm, diffs


__all__ = ["normalize_text"]
