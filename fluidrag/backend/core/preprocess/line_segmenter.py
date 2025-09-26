"""Line join/split helpers for preprocessing."""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional


_APPENDIX_PREFIX_RX = re.compile(r"^\s*A[1-9][.\u2024\u2027\uFF0E]?\s*$")


def join_split_lines(lines: Iterable[Dict], debug: Optional[List[Dict]] = None) -> List[Dict]:
    """Apply header-specific join/split rules to preprocessed lines."""

    normalised = list(lines)
    if not normalised:
        return []

    output: List[Dict] = []
    idx = 0

    while idx < len(normalised):
        line = dict(normalised[idx])
        text = line.get("text_norm", "")

        attempted_join = False
        joined = False
        nxt = None

        # Join wrapped headers such as ``"A5."`` followed by ``"Utilities"``.
        if _looks_header_prefix(text) and idx + 1 < len(normalised):
            nxt = dict(normalised[idx + 1])
            title = nxt.get("text_norm", "")
            attempted_join = True
            if _should_join_header_prefix(text, title):
                joined = True
                joined_text = f"{text.strip()} {title.lstrip()}".strip()
                joined_raw = f"{(line.get('text_raw') or '').strip()} {(nxt.get('text_raw') or '').lstrip()}".strip()
                line["text_norm"] = joined_text
                if joined_raw:
                    line["text_raw"] = joined_raw
                line.setdefault("join_from", [])
                line["join_from"].extend(
                    filter(lambda v: v is not None, [line.get("line_idx"), nxt.get("line_idx")])
                )
                line["bbox"] = _union_bbox(line.get("bbox"), nxt.get("bbox"))
                idx += 2
                output.append(line)
            else:
                output.append(line)
                idx += 1
        else:
            # Split lines that contain two appendix headers on the same row.
            if _has_two_header_tokens(text):
                splits = _split_two_headers(line)
                output.extend(splits)
                if debug is not None:
                    debug.append(
                        {
                            "marker": "header_split",
                            "line_idx": line.get("line_idx"),
                            "page": line.get("page"),
                            "text_norm": text,
                            "parts": [entry.get("text_norm") for entry in splits],
                        }
                    )
                idx += 1
            else:
                output.append(line)
                idx += 1

        if debug is not None and attempted_join:
            debug.append(
                {
                    "marker": "soft_unwrap_attempt",
                    "joined": joined,
                    "line_idx": line.get("line_idx"),
                    "next_line_idx": (nxt or {}).get("line_idx"),
                    "page": line.get("page"),
                    "prefix_text": text,
                    "next_text": (nxt or {}).get("text_norm"),
                    "tail_tokens": len(((nxt or {}).get("text_norm") or "").split()),
                }
            )
            if joined and nxt is not None:
                debug.append(
                    {
                        "marker": "line_skip",
                        "skip_reason": "merged_into_prev",
                        "line_idx": nxt.get("line_idx"),
                        "page": nxt.get("page"),
                        "text_norm": nxt.get("text_norm"),
                        "text_raw": nxt.get("text_raw"),
                    }
                )

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


def _should_join_header_prefix(prefix: str, tail: str) -> bool:
    prefix = (prefix or "").strip()
    tail = (tail or "").strip()
    if not tail:
        return False
    if _APPENDIX_PREFIX_RX.match(prefix):
        return True
    if _looks_title_like(tail):
        return True
    tokens = tail.split()
    if not tokens:
        return False
    head = tokens[0]
    if not head or not head[0].isupper():
        return False
    return len(tokens) <= 6


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
