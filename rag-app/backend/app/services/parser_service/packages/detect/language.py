"""Language detection heuristics."""
from __future__ import annotations

import re
from collections import Counter


def detect_language(text: str) -> str:
    letters = re.findall(r"[a-zA-Z]", text)
    if not letters:
        return "unknown"
    counter = Counter(ch.lower() for ch in letters)
    common = counter.most_common(1)[0][0]
    if common in "abcdefghijklmnopqrstuvwxyz":
        return "en"
    return "unknown"
