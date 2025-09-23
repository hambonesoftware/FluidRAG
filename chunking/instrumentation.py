"""Utilities for instrumenting chunking stages and computing diagnostics."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Dict, List, Sequence, Tuple

MAIN_HEADING_RE = re.compile(r"(?m)^(?P<num>\d+)\)\s+[^\n]+$")
APPENDIX_HEADING_RE = re.compile(r"(?m)^A(?P<anum>\d+)\.\s+[^\n]+$")
APPENDIX_BLOCK_RE = re.compile(r"(?m)^Appendix\s+[A-D]\s+—\s+[^\n]+$")

ARTIFACT_RE = re.compile(r"\s*(?:[0-9]{1,3}|[•\-]|i|ii|iii|iv|v)\s*$", re.IGNORECASE)


@dataclass
class ChunkDiagnostics:
    chunk_id: str
    chunk_index: int
    section_number: str | None
    has_heading: bool
    cross_heading: bool
    artifact_lines: int
    total_lines: int
    appendix_weight: int
    detected_headings: Sequence[str]


def token_count(text: str) -> int:
    return len([t for t in text.split() if t])


def is_artifact(line: str) -> bool:
    return bool(ARTIFACT_RE.fullmatch(line.strip()))


def detect_heading_spans(text: str) -> List[Tuple[str, int, int]]:
    spans: List[Tuple[str, int, int]] = []
    for matcher in (MAIN_HEADING_RE, APPENDIX_HEADING_RE, APPENDIX_BLOCK_RE):
        for match in matcher.finditer(text):
            sec_id = match.groupdict().get("num") or match.groupdict().get("anum")
            label = match.group(0).strip()
            spans.append((sec_id or label, match.start(), match.end()))
    spans.sort(key=lambda item: item[1])
    return spans


def first_non_artifact_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip() and not is_artifact(line):
            return line.strip()
    return ""


def _appendix_weight(lines: Sequence[str]) -> int:
    weight = 0
    run = 0
    for line in lines:
        tokens = [tok for tok in re.split(r"\s{2,}|\t", line.strip()) if tok]
        if len(tokens) >= 3 and any(tok.isdigit() for tok in tokens):
            run += 1
            if run >= 4:
                weight += 1
        else:
            run = 0
    return weight


def summarize_chunks(chunks: Sequence[Dict]) -> Tuple[Dict[str, float], List[ChunkDiagnostics]]:
    diagnostics: List[ChunkDiagnostics] = []
    if not chunks:
        return {
            "chunk_count": 0,
            "avg_chars": 0.0,
            "avg_tokens": 0.0,
            "avg_heading_span": 0.0,
            "pct_chunks_with_heading": 0.0,
            "pct_chunks_cross_heading": 0.0,
            "pct_page_artifact_lines": 0.0,
            "section_coverage": [],
            "appendix_weight": 0,
        }, diagnostics

    section_coverage: List[str] = []
    appendix_weight_total = 0
    cross_heading_count = 0
    heading_count = 0
    artifact_lines_total = 0
    total_lines = 0
    heading_span_values: List[int] = []

    for idx, chunk in enumerate(chunks):
        text = chunk.get("text", "") or ""
        lines = text.splitlines()
        headings = detect_heading_spans(text)
        normalized_section = (chunk.get("section_number") or chunk.get("section_id") or "").strip()
        if normalized_section and normalized_section not in section_coverage:
            section_coverage.append(normalized_section)
        has_heading = bool(normalized_section or headings)
        heading_count += int(has_heading)
        unique_heading_labels = sorted({label for label, *_ in headings})
        cross_heading = len(unique_heading_labels) >= 2
        cross_heading_count += int(cross_heading)
        artifact_lines = sum(1 for line in lines if is_artifact(line))
        artifact_lines_total += artifact_lines
        total_lines += max(1, len(lines))
        appendix_weight_total += _appendix_weight(lines)
        heading_span_values.append(len(unique_heading_labels))
        diagnostics.append(
            ChunkDiagnostics(
                chunk_id=str(chunk.get("id") or f"idx-{idx}"),
                chunk_index=idx,
                section_number=normalized_section or None,
                has_heading=has_heading,
                cross_heading=cross_heading,
                artifact_lines=artifact_lines,
                total_lines=max(1, len(lines)),
                appendix_weight=_appendix_weight(lines),
                detected_headings=unique_heading_labels,
            )
        )

    chunk_count = len(chunks)
    avg_chars = mean(len((chunk.get("text") or "")) for chunk in chunks)
    avg_tokens = mean(token_count(chunk.get("text", "")) for chunk in chunks)
    avg_heading_span = mean(heading_span_values)
    pct_chunks_with_heading = heading_count / chunk_count * 100.0
    pct_chunks_cross_heading = cross_heading_count / chunk_count * 100.0
    pct_page_artifact_lines = (artifact_lines_total / total_lines) * 100.0 if total_lines else 0.0

    metrics = {
        "chunk_count": chunk_count,
        "avg_chars": avg_chars,
        "avg_tokens": avg_tokens,
        "avg_heading_span": avg_heading_span,
        "pct_chunks_with_heading": pct_chunks_with_heading,
        "pct_chunks_cross_heading": pct_chunks_cross_heading,
        "pct_page_artifact_lines": pct_page_artifact_lines,
        "section_coverage": section_coverage,
        "appendix_weight": appendix_weight_total,
    }
    return metrics, diagnostics


def instrument_doc(doc_id: str, stage_chunks: Dict[str, Sequence[Dict]], out_dir: Path) -> Dict[str, Dict[str, float]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: Dict[str, Dict[str, float]] = {}
    record = {"doc_id": doc_id, "stages": {}, "chunks": {}}
    for stage, chunks in stage_chunks.items():
        metrics, diagnostics = summarize_chunks(chunks)
        summary[stage] = metrics
        record["stages"][stage] = metrics
        record["chunks"][stage] = [diag.__dict__ for diag in diagnostics]
    outfile = out_dir / f"{doc_id}.jsonl"
    with outfile.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return summary


def render_chunk_diff(before: Sequence[Dict], after: Sequence[Dict], context: int = 1) -> List[Dict[str, object]]:
    """Return a light-weight diff structure for before/after chunks."""
    max_len = max(len(before), len(after))
    diff_rows: List[Dict[str, object]] = []
    for idx in range(max_len):
        before_chunk = before[idx] if idx < len(before) else None
        after_chunk = after[idx] if idx < len(after) else None
        row = {
            "index": idx,
            "before_id": before_chunk.get("id") if before_chunk else None,
            "after_id": after_chunk.get("id") if after_chunk else None,
            "before_preview": _preview(before_chunk.get("text") if before_chunk else "", context),
            "after_preview": _preview(after_chunk.get("text") if after_chunk else "", context),
        }
        diff_rows.append(row)
    return diff_rows


def _preview(text: str, context: int) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    if len(lines) <= context * 2:
        return " ".join(lines)
    head = lines[:context]
    tail = lines[-context:]
    return " ... ".join([" ".join(head), " ".join(tail)])
