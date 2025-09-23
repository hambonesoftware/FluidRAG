"""Heuristic chunk transformation rules."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Sequence

from .instrumentation import (
    APPENDIX_BLOCK_RE,
    APPENDIX_HEADING_RE,
    MAIN_HEADING_RE,
    detect_heading_spans,
    first_non_artifact_line,
    is_artifact,
    token_count,
)


@dataclass
class RuleConfig:
    hard_heading_breaks: bool = True
    page_footer_scrub: bool = True
    list_stitching: bool = True
    appendix_microchunking: bool = True
    soft_split_on_view: bool = True


BULLET_PREFIXES = ("- ", "• ", "* ")


def apply_rules(chunks: Sequence[Dict], config: RuleConfig | Dict) -> List[Dict]:
    cfg = config if isinstance(config, RuleConfig) else RuleConfig(**config)
    processed: List[Dict] = []
    for chunk in chunks:
        cleaned = dict(chunk)
        if cfg.page_footer_scrub:
            cleaned["text"] = _scrub_artifacts(cleaned.get("text", ""))
        if cfg.list_stitching:
            cleaned["text"] = _stitch_lists(cleaned.get("text", ""))
        if cfg.hard_heading_breaks:
            splitted = _split_on_headings(cleaned)
        else:
            splitted = [cleaned]
        for piece in splitted:
            processed.append(piece)
    if cfg.appendix_microchunking:
        processed = _microchunk_appendix(processed)
    return processed


def _scrub_artifacts(text: str) -> str:
    lines = text.splitlines()
    cleaned: List[str] = []
    for line in lines:
        if line.strip() and is_artifact(line) and not _has_inline_text(line):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def _has_inline_text(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    for prefix in BULLET_PREFIXES:
        if stripped.startswith(prefix) and len(stripped) > len(prefix):
            return True
    if re.fullmatch(r"(i|ii|iii|iv|v)", stripped, re.IGNORECASE):
        return False
    return any(ch.isalpha() for ch in stripped)


def _stitch_lists(text: str) -> str:
    lines = text.splitlines()
    stitched: List[str] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        stripped = line.lstrip()
        if _is_bullet(stripped):
            current = line.rstrip()
            j = idx + 1
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip():
                    break
                if _is_heading_line(nxt):
                    break
                if current.endswith(tuple(".;:?!")):
                    break
                if nxt and nxt[0].isupper():
                    break
                current = current.rstrip() + " " + nxt.strip()
                j += 1
            stitched.append(current)
            idx = j
            continue
        stitched.append(line)
        idx += 1
    return "\n".join(stitched)


def _is_heading_line(line: str) -> bool:
    return bool(MAIN_HEADING_RE.match(line) or APPENDIX_HEADING_RE.match(line) or APPENDIX_BLOCK_RE.match(line))


def _is_bullet(line: str) -> bool:
    stripped = line.strip()
    return any(stripped.startswith(prefix) for prefix in BULLET_PREFIXES)


def _split_on_headings(chunk: Dict) -> List[Dict]:
    text = chunk.get("text", "") or ""
    spans = detect_heading_spans(text)
    if len(spans) <= 1:
        return [chunk]
    pieces: List[Dict] = []
    lines = text.splitlines()
    indices = [0]
    for _, start, _ in spans[1:]:
        indices.append(_line_index_for_offset(lines, start))
    indices.append(len(lines))
    for idx in range(len(indices) - 1):
        start = indices[idx]
        end = indices[idx + 1]
        part_lines = lines[start:end]
        if not part_lines:
            continue
        part = dict(chunk)
        part_text = "\n".join(part_lines)
        part["text"] = part_text
        heading_line = first_non_artifact_line(part_text)
        section_match = MAIN_HEADING_RE.match(heading_line) or APPENDIX_HEADING_RE.match(heading_line)
        if section_match:
            part["section_number"] = section_match.groupdict().get("num") or section_match.groupdict().get("anum")
        part.setdefault("meta", {}).update({"hard_heading_split": True})
        part["id"] = f"{chunk.get('id', 'chunk')}::{idx}"
        pieces.append(part)
    return pieces or [chunk]


def _line_index_for_offset(lines: Sequence[str], offset: int) -> int:
    running = 0
    for idx, line in enumerate(lines):
        running += len(line) + 1
        if running > offset:
            return idx
    return len(lines)


def _microchunk_appendix(chunks: Sequence[Dict]) -> List[Dict]:
    result: List[Dict] = []
    for chunk in chunks:
        heading = first_non_artifact_line(chunk.get("text", ""))
        if heading.startswith("Appendix B"):
            result.extend(_split_table(chunk, {"Line", "Item", "Description", "Qty", "Unit"}))
        elif heading.startswith("Appendix C"):
            result.extend(_split_table(chunk, {"Milestone", "Target", "Weeks", "Notes"}))
        elif heading.startswith("Appendix D"):
            result.extend(_split_table(chunk, {"Section", "Requirement", "Compliant", "Notes"}))
        else:
            result.append(chunk)
    return result


def _split_table(chunk: Dict, header_tokens: set[str]) -> List[Dict]:
    lines = [line for line in chunk.get("text", "").splitlines() if line.strip()]
    if not lines:
        return [chunk]
    header_idx = None
    for idx, line in enumerate(lines):
        tokens = set(re.split(r"\s{2,}|\t", line.strip()))
        if header_tokens <= tokens:
            header_idx = idx
            break
    if header_idx is None:
        return [chunk]
    rows = lines[header_idx + 1 :]
    chunks_out: List[Dict] = []
    row_buffer: List[str] = []
    for line in rows:
        if re.match(r"^[-–]{2,}$", line.strip()):
            continue
        if _looks_like_new_row(line):
            if row_buffer:
                chunks_out.append(_emit_table_chunk(chunk, header_idx, row_buffer))
            row_buffer = [line]
        else:
            row_buffer.append(line)
    if row_buffer:
        chunks_out.append(_emit_table_chunk(chunk, header_idx, row_buffer))
    return chunks_out or [chunk]


def _emit_table_chunk(parent: Dict, header_idx: int, rows: Sequence[str]) -> Dict:
    part = dict(parent)
    header = parent.get("text", "").splitlines()[header_idx]
    part["text"] = "\n".join([header] + list(rows))
    part["chunk_type"] = "table_row"
    part["tokens"] = token_count(part["text"])
    part.setdefault("meta", {}).update({"appendix_microchunk": True})
    part["id"] = f"{parent.get('id', 'chunk')}::tbl::{hash(tuple(rows)) & 0xffff:x}"
    return part


def _looks_like_new_row(line: str) -> bool:
    tokens = [tok for tok in re.split(r"\s{2,}|\t", line.strip()) if tok]
    if len(tokens) >= 3 and any(tok.isdigit() for tok in tokens):
        return True
    if tokens and tokens[0].isdigit():
        return True
    return False


def soft_split_on_headings(chunk: Dict, allowed_sections: Sequence[str] | set[str]) -> List[Dict]:
    allowed = set(allowed_sections)
    spans = detect_heading_spans(chunk.get("text", ""))
    if not spans:
        return [chunk]
    pieces: List[Dict] = []
    for idx, (section_id, start, end) in enumerate(spans):
        if allowed and section_id not in allowed:
            continue
        part = dict(chunk)
        part["text"] = chunk["text"][start: spans[idx + 1][1] if idx + 1 < len(spans) else len(chunk["text"])].strip()
        part["section_number"] = section_id
        part.setdefault("meta", {}).update({"soft_split": True})
        part["id"] = f"{chunk.get('id', 'chunk')}::soft::{idx}"
        pieces.append(part)
    return pieces or [chunk]
