"""Line join/split helpers for preprocessing."""
from __future__ import annotations

from typing import Dict, Iterable, List


def join_split_lines(lines: Iterable[Dict]) -> List[Dict]:
    """Apply header-specific join/split rules to preprocessed lines."""

    normalised = list(lines)
    if not normalised:
        return []

    output: List[Dict] = []
    idx = 0

    while idx < len(normalised):
        line = dict(normalised[idx])
        text = line.get("text_norm", "")

        # Join wrapped headers such as ``"A5."`` followed by ``"Utilities"``.
        if _looks_header_prefix(text) and idx + 1 < len(normalised):
            nxt = normalised[idx + 1]
            title = nxt.get("text_norm", "")
            if _looks_title_like(title):
                joined_text = f"{text.strip()} {title.lstrip()}".strip()
                line["text_norm"] = joined_text
                line.setdefault("join_from", [])
                line["join_from"].extend(filter(lambda v: v is not None, [line.get("line_idx"), nxt.get("line_idx")]))
                line["bbox"] = _union_bbox(line.get("bbox"), nxt.get("bbox"))
                idx += 2
                output.append(line)
                continue

        # Split lines that contain two appendix headers on the same row.
        if _has_two_header_tokens(text):
            output.extend(_split_two_headers(line))
            idx += 1
            continue

        output.append(line)
        idx += 1

    return output


def _looks_header_prefix(text: str) -> bool:
    text = text.strip()
    if len(text) < 2:
        return False
    if text.endswith(".") and len(text) <= 4:
        head = text[:-1]
        return head and head[0].isalpha() and head[1:].isdigit()
    if text.endswith(")") and len(text) <= 4:
        return text[:-1].isdigit()
    return False


def _looks_title_like(text: str) -> bool:
    text = text.strip()
    return bool(text) and text[0].isupper() and len(text) > 4


def _has_two_header_tokens(text: str) -> bool:
    import re

    return len(re.findall(r"[A-Z]\d+\.", text)) >= 2


def _split_two_headers(line: Dict) -> List[Dict]:
    import re

    parts = [segment.strip() for segment in re.split(r"(?=[A-Z]\d+\.)", line.get("text_norm", "")) if segment.strip()]
    split_lines: List[Dict] = []
    for part in parts:
        new_line = dict(line)
        new_line["text_norm"] = part
        new_line["split_of"] = line.get("line_idx")
        split_lines.append(new_line)
    return split_lines


def _union_bbox(a, b):
    if not a:
        return b
    if not b:
        return a
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


__all__ = ["join_split_lines"]
