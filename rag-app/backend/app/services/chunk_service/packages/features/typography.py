"""Typography feature extraction."""
from __future__ import annotations

from typing import Dict


def extract_typography(text: str) -> Dict[str, float]:
    lines = [line for line in text.splitlines() if line.strip()]
    uppercase_ratio = sum(1 for ch in text if ch.isupper()) / (len(text) or 1)
    bullet_ratio = sum(1 for line in lines if line.strip().startswith(('-', '*'))) / (len(lines) or 1)
    return {"uppercase_ratio": uppercase_ratio, "bullet_ratio": bullet_ratio}
