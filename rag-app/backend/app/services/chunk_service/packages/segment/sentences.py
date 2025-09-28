"""Sentence segmentation."""
from __future__ import annotations

import re
from typing import List


_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]?")


def split_sentences(text: str) -> List[str]:
    sentences = [match.group(0).strip() for match in _SENTENCE_RE.finditer(text)]
    return [sentence for sentence in sentences if sentence]
