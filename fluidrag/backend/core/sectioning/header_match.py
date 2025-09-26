"""Regex helpers for classifying header candidates."""
from __future__ import annotations

import re
from typing import Dict

NUMERIC_RE = re.compile(r"^\s*(\d{1,3})\)\s+(.+?)\s*$")
APPENDIX_RE = re.compile(r"^\s*([A-Z])(\d{1,3})\.\s{0,2}(.+?)\s*$")


def label_caps_ok(text: str, caps_ratio: float) -> bool:
    if caps_ratio < 0.60:
        return False
    if text.endswith("."):
        return False
    if " " not in text.strip():
        return False
    return True


def classify_line(text_norm: str, caps_ratio: float) -> Dict[str, str]:
    match = NUMERIC_RE.match(text_norm)
    if match:
        return {"kind": "numeric", "number": match.group(1), "title": match.group(2)}

    match = APPENDIX_RE.match(text_norm)
    if match:
        return {
            "kind": "appendix",
            "letter": match.group(1),
            "number": match.group(2),
            "title": match.group(3),
        }

    if label_caps_ok(text_norm, caps_ratio):
        return {"kind": "label", "title": text_norm}

    return {"kind": "none"}


__all__ = ["classify_line", "label_caps_ok"]
