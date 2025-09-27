"""End-to-end ultrafine (UF) pipeline orchestration.

The helpers in this module wire together the PDF ingestion, UF chunking,
EFHG scoring, header detection, table extraction, and retrieval index
construction described in the ultrafine specification.  The implementation
leans on the existing building blocks in the repository (``pdf_extract``,
``ingest.microchunker``, ``chunking.efhg`` and the header repair module) while
adding the glue required to produce deterministic artefacts and observability
reports for each stage.

The public entry-point is :func:`run_pipeline` which returns a
``PipelineResult`` data class containing the enriched UF chunks, EFHG span
scores, verified headers, table metadata, retrieval index summaries, and the
paths to all generated sidecar files.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import statistics
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

import regex as re

from chunking.efhg import compute_chunk_scores, compute_fluid_neighbors, run_efhg
from ingest.microchunker import MicroChunk, microchunk_text

from ..ingest.pdf_extract import extract as pdf_extract
from ..parse.header_sequence_repair import aggressive_sequence_repair
from ..headers import config as header_cfg
from ..headers.header_llm import (
    VerifiedHeaders,
    build_header_prompt,
    parse_fenced_outline,
    verify_headers,
)
from index import BM25Store, EmbeddingStore

LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalisation helpers & tokenisation
# ---------------------------------------------------------------------------

_DOT_VARIANTS = "\u2024\u2027\uFF0E"
_SPACE_VARIANTS = "\u00A0\u2002\u2003\u2009\u200A\u202F\u205F\u3000"
_ZERO_WIDTH = "\u200B\u200C\u200D\u2060\uFEFF"
_TOKEN_RX = re.compile(r"\p{L}[\p{L}\p{Mn}\p{Mc}\p{Pd}\p{Pc}\p{Nd}]*|\p{N}+|[^\s]", re.UNICODE)
_HEADER_MARK_RX = re.compile(r"^\s*(?:\d+\)|[A-Z]\d+\.)")
_FILL_LINE_RX = re.compile(r"_{3,}\s*$")
_BULLET_RX = re.compile(r"^\s*(?:[-*\u2022\u2023\u2043]|[A-Za-z]{1,3}\)|[A-Za-z]{1,3}\.)\s+")
_NUMBERED_RX = re.compile(r"^\s*(?:\d{1,3}(?:[.)]|(?:\.\d+)*\.)|\d{1,3}\))\s+")
_TABLE_ROW_RX = re.compile(r"(?:\t|\s{2,}\S)\s{2,}\S")
_GUTTER_TOLERANCE = 8.0


def _classify_trailing_punct(text: str) -> Optional[str]:
    if not text:
        return None
    stripped = text.rstrip()
    if not stripped:
        return None
    if _FILL_LINE_RX.search(stripped):
        return "_FILL"
    tail = stripped[-1]
    if tail in {".", ",", ":", ";", ")", "]"}:
        return tail
    return None


def _detect_list_context(text: str) -> str:
    if not text:
        return "none"
    stripped = text.strip()
    if not stripped:
        return "none"
    if _TABLE_ROW_RX.search(text):
        return "table_row"
    if _BULLET_RX.match(stripped):
        return "bullet"
    if _NUMBERED_RX.match(stripped):
        return "numbered"
    return "none"


def _normalise_spaces(text: str) -> str:
    for ch in _SPACE_VARIANTS:
        text = text.replace(ch, " ")
    for ch in _ZERO_WIDTH:
        text = text.replace(ch, "")
    for ch in _DOT_VARIANTS:
        text = text.replace(ch, ".")
    return text


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalise_text(text: str) -> str:
    return _collapse_ws(_normalise_spaces(text or ""))


def _json_sanitise(value: Any, *, depth: int = 0) -> Any:
    """Return ``value`` in a JSON-serialisable form."""

    if depth > 8:
        return repr(value)
    if isinstance(value, Mapping):
        return {str(key): _json_sanitise(val, depth=depth + 1) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_sanitise(item, depth=depth + 1) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        json.dumps(value)
        return value
    except TypeError:
        return repr(value)


def _tokenise_with_offsets(text: str, *, base_offset: int = 0) -> List[Dict[str, Any]]:
    tokens: List[Dict[str, Any]] = []
    for match in _TOKEN_RX.finditer(text or ""):
        start, end = match.span()
        tokens.append(
            {
                "text": match.group(0),
                "char_start": base_offset + start,
                "char_end": base_offset + end,
            }
        )
    return tokens


# ---------------------------------------------------------------------------
# Dataclasses for structured return values
# ---------------------------------------------------------------------------


@dataclass
class PageRecord:
    page_number: int
    raw_text: str
    norm_text: str
    lines: List[str]
    line_styles: List[Mapping[str, Any]]
    line_models: List[Mapping[str, Any]]
    line_offsets: List[int]
    tokens: List[Dict[str, Any]]


@dataclass
class IngestResult:
    doc_id: str
    pages: List[PageRecord]
    parts: List[Mapping[str, Any]]
    layout_blocks: List[Mapping[str, Any]]
    tables: List[Mapping[str, Any]]
    page_artifacts: Dict[str, Path]


@dataclass
class HeaderResult:
    headers: List[Dict[str, Any]]
    pages: List[Dict[str, Any]]
    repairs: List[Dict[str, Any]]
    header_shards: List[Dict[str, Any]]
    artifacts: Dict[str, Path]
    audit: Dict[str, Any]


@dataclass
class RetrievalSummary:
    micro_index_size: int
    header_shard_count: int
    table_count: int
    bm25_path: Optional[Path]
    embedding_path: Optional[Path]
    header_bm25_path: Optional[Path]
    header_embedding_path: Optional[Path]
    table_bm25_path: Optional[Path]
    table_embedding_path: Optional[Path]
    span_index_path: Optional[Path]
    header_doc_path: Optional[Path]
    table_doc_path: Optional[Path]


@dataclass
class PipelineResult:
    uf_chunks: List[MicroChunk]
    chunk_scores: List[Dict[str, Any]]
    efhg_spans: List[Dict[str, Any]]
    headers: HeaderResult
    tables: List[Dict[str, Any]]
    retrieval: RetrievalSummary
    artifacts: Dict[str, Path]
    audits: Dict[str, Any]

    def summary(self) -> Dict[str, Any]:
        """Return a JSON-serialisable summary for API responses or caching."""

        score_values = [entry.get("score") for entry in self.efhg_spans if entry.get("score") is not None]
        max_score = max(score_values) if score_values else None
        min_score = min(score_values) if score_values else None
        return {
            "chunk_count": len(self.uf_chunks),
            "efhg_span_count": len(self.efhg_spans),
            "header_count": len(self.headers.headers),
            "table_count": len(self.tables),
            "retrieval": {
                "micro_index_size": self.retrieval.micro_index_size,
                "header_shard_count": self.retrieval.header_shard_count,
                "table_count": self.retrieval.table_count,
            },
            "spans": {
                "min_score": min_score,
                "max_score": max_score,
            },
            "artifacts": {key: str(path) for key, path in self.artifacts.items()},
        }


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return path


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def _write_overlay_svg(path: Path, blocks: Sequence[Mapping[str, Any]]) -> Path:
    """Render a lightweight SVG overlay for debug inspection."""

    import xml.etree.ElementTree as ET

    width = 1024
    height = 1024
    root = ET.Element(
        "svg",
        attrib={
            "xmlns": "http://www.w3.org/2000/svg",
            "width": str(width),
            "height": str(height),
            "viewBox": f"0 0 {width} {height}",
        },
    )
    for block in blocks or []:
        bbox = block.get("bbox") or [0, 0, 0, 0]
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        x0, y0, x1, y1 = bbox
        if x1 <= x0 or y1 <= y0:
            continue
        page = int(block.get("page") or 1)
        group = ET.SubElement(root, "g", attrib={"data-page": str(page)})
        rect = ET.SubElement(
            group,
            "rect",
            attrib={
                "x": f"{float(x0):.2f}",
                "y": f"{float(y0):.2f}",
                "width": f"{float(x1 - x0):.2f}",
                "height": f"{float(y1 - y0):.2f}",
                "fill": "none",
                "stroke": "#ff4081",
                "stroke-width": "0.8",
            },
        )
        rect.tail = None
    tree = ET.ElementTree(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(path, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# PDF ingestion & UF chunk preparation
# ---------------------------------------------------------------------------


def _ingest_pdf(
    pdf_path: str,
    *,
    doc_id: str,
    sidecar_dir: Path,
    pre_extracted: Optional[Mapping[str, Any]] = None,
) -> IngestResult:
    """Run the extraction stack and prepare per-line metadata for chunking."""

    if pre_extracted is None:
        layout = pdf_extract(pdf_path, str(sidecar_dir))
    else:
        layout = dict(pre_extracted)

    pages_linear = layout.get("pages_linear") or []
    pages_lines = layout.get("pages_lines") or [page.splitlines() for page in pages_linear]
    page_styles = layout.get("page_line_styles") or [
        [{} for _ in page] for page in pages_lines
    ]
    layout_blocks = layout.get("layout_blocks") or []
    tables = layout.get("tables") or []

    page_records: List[PageRecord] = []
    parts: List[Mapping[str, Any]] = []
    jsonl_rows: List[Dict[str, Any]] = []

    for page_idx, lines in enumerate(pages_lines, start=1):
        styles_src = page_styles[page_idx - 1] if page_idx - 1 < len(page_styles) else [{} for _ in lines]
        joined = "\n".join(lines)
        norm = _normalise_text(joined)
        offsets: List[int] = []
        tokens: List[Dict[str, Any]] = []
        cursor = 0
        line_entries: List[Dict[str, Any]] = []
        line_models: List[Dict[str, Any]] = []
        styles_out: List[Dict[str, Any]] = []
        prev_meta: Optional[Dict[str, Any]] = None
        median_buf: deque[float] = deque(maxlen=25)
        prev_end_offset = 0
        for line_idx, line in enumerate(lines):
            base_style = styles_src[line_idx] if line_idx < len(styles_src) else {}
            style = dict(base_style or {})
            start_offset = cursor
            offsets.append(start_offset)
            line_tokens = _tokenise_with_offsets(line, base_offset=start_offset)
            tokens.extend({**token, "line_idx": line_idx} for token in line_tokens)

            bbox = style.get("bbox") if isinstance(style, Mapping) else None
            left_x = None
            y_top = None
            y_bottom = None
            if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                try:
                    left_x = float(bbox[0])
                except Exception:  # pragma: no cover - defensive
                    left_x = None
                try:
                    y_top = float(bbox[1])
                    y_bottom = float(bbox[3])
                except Exception:  # pragma: no cover - defensive
                    y_top = y_bottom = None

            font_pt_raw = style.get("font_pt", style.get("font_size"))
            try:
                font_pt = float(font_pt_raw) if font_pt_raw is not None else 0.0
            except Exception:
                font_pt = 0.0
            bold_flag = bool(style.get("bold"))

            line_height = 0.0
            if y_top is not None and y_bottom is not None:
                line_height = float(y_bottom - y_top)
            elif prev_meta and prev_meta.get("line_height"):
                line_height = float(prev_meta["line_height"])

            if median_buf:
                median_gap = statistics.median(median_buf)
            else:
                baseline = prev_meta.get("line_height") if prev_meta else None
                median_gap = float(baseline) if baseline else (line_height if line_height > 0 else 1.0)
            if median_gap <= 0:
                median_gap = line_height if line_height > 0 else 1.0

            prev_trailing = prev_meta.get("trailing_punct") if prev_meta else None
            prev_font = prev_meta.get("font_pt") if prev_meta else None
            prev_left = prev_meta.get("left_x") if prev_meta else None
            prev_bottom = prev_meta.get("y_bottom") if prev_meta else None

            if prev_font is not None:
                try:
                    font_delta = float(font_pt - float(prev_font))
                except Exception:
                    font_delta = 0.0
            else:
                font_delta = 0.0
            bold_flip = bool(prev_meta and bool(prev_meta.get("bold")) != bold_flag)
            if left_x is not None and prev_left is not None:
                try:
                    left_x_delta = float(left_x - float(prev_left))
                except Exception:
                    left_x_delta = 0.0
            else:
                left_x_delta = 0.0

            if y_top is not None and prev_bottom is not None:
                try:
                    y_gap = float(y_top - float(prev_bottom))
                except Exception:
                    y_gap = 0.0
            else:
                y_gap = 0.0

            big_gap = y_gap > 1.6 * median_gap if median_gap > 0 else y_gap > 0
            hard_newline = (start_offset - prev_end_offset) >= 2 if line_idx > 0 else False
            style_break = bool(bold_flip or abs(font_delta) >= 1.0 or abs(left_x_delta) > _GUTTER_TOLERANCE)

            virtual_blanks = 1 if big_gap else 0
            if hard_newline:
                virtual_blanks += 1
            if median_gap > 0:
                huge_gap = y_gap > 2.2 * median_gap
            else:
                huge_gap = y_gap > 0
            if huge_gap:
                virtual_blanks = max(virtual_blanks, 2)

            para_start = bool(
                hard_newline
                or big_gap
                or style_break
                or (prev_trailing in {".", "_FILL", ":"})
            )

            is_blank = not (line.strip())
            list_context = _detect_list_context(line)
            newline_count = (start_offset - prev_end_offset) if line_idx > 0 else 0

            style_jump = {
                "font_delta": font_delta,
                "bold_flip": bold_flip,
                "left_x_delta": left_x_delta,
            }

            style.setdefault("font_pt", font_pt)
            if left_x is not None:
                style.setdefault("left_x", left_x)
            if line_height:
                style.setdefault("line_height", line_height)
            styles_out.append(dict(style))

            line_entry = {
                "page": page_idx,
                "index": line_idx,
                "text": line,
                "norm_text": _normalise_text(line),
                "style": style,
                "tokens": line_tokens,
                "break_reason": "line_break",
                "is_blank": bool(is_blank),
                "newline_count": int(newline_count),
                "y_gap": float(y_gap),
                "line_height": float(line_height),
                "virtual_blank_lines_before": int(virtual_blanks),
                "style_jump": dict(style_jump),
                "para_start": bool(para_start),
                "prev_trailing_punct": prev_trailing,
                "list_context": list_context,
                "left_x": float(left_x) if left_x is not None else None,
                "font_pt": float(font_pt),
                "bold": bool(bold_flag),
            }
            line_entries.append(line_entry)

            line_models.append(
                {
                    "page": page_idx,
                    "index": line_idx,
                    "text": line,
                    "norm_text": line_entry["norm_text"],
                    "is_blank": bool(is_blank),
                    "newline_count": int(newline_count),
                    "y_gap": float(y_gap),
                    "line_height": float(line_height),
                    "virtual_blank_lines_before": int(virtual_blanks),
                    "style_jump": dict(style_jump),
                    "para_start": bool(para_start),
                    "prev_trailing_punct": prev_trailing,
                    "list_context": list_context,
                    "left_x": float(left_x) if left_x is not None else None,
                    "font_pt": float(font_pt),
                    "bold": bool(bold_flag),
                }
            )

            indent = None
            if left_x is not None:
                indent = left_x
            part = {
                "doc_id": doc_id,
                "text": line,
                "page": page_idx,
                "line_idx": line_idx,
                "font_size": style.get("font_size", font_pt),
                "font_pt": font_pt,
                "font_weight": style.get("font_weight"),
                "bold": bold_flag,
                "indent": indent,
                "break_reason": "line_break",
                "header_anchor": bool(_HEADER_MARK_RX.match(line.strip())),
                "is_blank": bool(is_blank),
                "newline_count": int(newline_count),
                "y_gap": float(y_gap),
                "line_height": float(line_height),
                "virtual_blank_lines_before": int(virtual_blanks),
                "style_jump": dict(style_jump),
                "para_start": bool(para_start),
                "prev_trailing_punct": prev_trailing,
                "list_context": list_context,
                "left_x": float(left_x) if left_x is not None else None,
            }
            parts.append(part)

            current_trailing = _classify_trailing_punct(line)
            prev_meta = {
                "font_pt": font_pt,
                "bold": bold_flag,
                "left_x": left_x,
                "y_bottom": y_bottom,
                "line_height": line_height,
                "trailing_punct": current_trailing,
            }
            prev_end_offset = start_offset + len(line)
            cursor = prev_end_offset + 1

            if line_height > 0:
                median_buf.append(float(line_height))
            elif prev_meta.get("line_height"):
                try:
                    median_buf.append(float(prev_meta["line_height"]))
                except Exception:  # pragma: no cover - defensive
                    median_buf.append(0.0)

        jsonl_rows.append(
            {
                "page": page_idx,
                "text": joined,
                "norm_text": norm,
                "lines": line_entries,
            }
        )
        page_records.append(
            PageRecord(
                page_number=page_idx,
                raw_text=joined,
                norm_text=norm,
                lines=list(lines),
                line_styles=styles_out,
                line_models=line_models,
                line_offsets=offsets,
                tokens=tokens,
            )
        )

    page_text_path = _write_jsonl(sidecar_dir / "uf_pipeline" / "page_text.jsonl", jsonl_rows)
    overlay_path = _write_overlay_svg(sidecar_dir / "uf_pipeline" / "page_overlay.svg", layout_blocks)

    artifacts = {
        "page_text": page_text_path,
        "page_overlay": overlay_path,
    }
    return IngestResult(
        doc_id=doc_id,
        pages=page_records,
        parts=parts,
        layout_blocks=layout_blocks,
        tables=tables,
        page_artifacts=artifacts,
    )


# ---------------------------------------------------------------------------
# Header pass helpers
# ---------------------------------------------------------------------------


def _fallback_headers(pages: Sequence[PageRecord]) -> List[Dict[str, Any]]:
    """Heuristic header extraction when no LLM client is provided."""

    headers: List[Dict[str, Any]] = []
    for page in pages:
        for line_idx, line in enumerate(page.lines):
            if not _HEADER_MARK_RX.match(line.strip()):
                continue
            label, text = _split_header_line(line)
            headers.append(
                {
                    "level": 1,
                    "label": label,
                    "text": text,
                    "page": page.page_number,
                    "confidence": 0.35,
                    "line_idx": line_idx,
                    "source": "heuristic",
                }
            )
    return headers


def _run_chat_sync(llm_client: Any, messages: Sequence[Mapping[str, Any]], **kwargs: Any) -> Any:
    """Execute ``llm_client.chat`` in a synchronous context."""

    async def _invoke() -> Any:
        return await llm_client.chat(messages, **kwargs)

    try:
        return asyncio.run(_invoke())
    except RuntimeError as exc:
        if "asyncio.run() cannot be called" not in str(exc):
            raise
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(_invoke())
        finally:
            asyncio.set_event_loop(None)
            loop.close()


def _extract_llm_payload(response: Any) -> Dict[str, Any]:
    """Best-effort extraction of a header payload from ``response``."""

    if isinstance(response, Mapping):
        for key in ("json", "data", "payload", "body", "response", "text"):
            value = response.get(key)
            if value is not None:
                return _extract_llm_payload(value)
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            message = first.get("message") if isinstance(first, Mapping) else None
            if isinstance(message, Mapping):
                return _extract_llm_payload(message.get("content"))
        return dict(response)
    if isinstance(response, str):
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            try:
                return parse_fenced_outline(response)
            except ValueError:
                return {}
    if isinstance(response, list):
        return {"headers": response}
    return {}


def _llm_headers(
    ingest: IngestResult,
    llm_client: Any,
) -> tuple[VerifiedHeaders, Optional[str], List[Dict[str, Any]], Dict[str, Any]]:
    """Invoke the header LLM pass and return verified headers and raw rows."""

    pages_norm = [page.norm_text for page in ingest.pages]
    pages_raw = [page.raw_text for page in ingest.pages]
    if not pages_norm:
        return VerifiedHeaders(), None, []

    messages = build_header_prompt(pages_norm)
    try:
        response = _run_chat_sync(
            llm_client,
            messages,
            temperature=0.0,
            max_tokens=1024,
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.warning("[UF pipeline] header LLM call failed: %s", exc)
        return VerifiedHeaders(), str(exc), [], {}

    payload = _extract_llm_payload(response)
    try:
        verified = verify_headers(payload, pages_norm, pages_raw)
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.warning("[UF pipeline] failed to verify LLM headers: %s", exc)
        return VerifiedHeaders(), str(exc), [], {
            "payload": _json_sanitise(payload),
            "raw_response": _json_sanitise(response),
        }

    rows = [
        {
            "label": header.label,
            "text": header.text,
            "page": header.page,
            "span": header.span,
            "verification": header.verification,
            "confidence": header.confidence,
            "source": header.source,
        }
        for header in verified.sorted()
    ]
    return (
        verified,
        None,
        rows,
        {
            "payload": _json_sanitise(payload),
            "raw_response": _json_sanitise(response),
        },
    )


def _llm_candidates_from_verified(verified: VerifiedHeaders) -> List[Dict[str, Any]]:
    """Convert verified LLM headers into candidate entries for verification."""

    candidates: List[Dict[str, Any]] = []
    for header in verified.sorted():
        candidates.append(
            {
                "level": None,
                "label": header.label,
                "text": header.text,
                "page": header.page,
                "confidence": header.confidence,
                "source": header.source,
            }
        )
    return candidates


def _split_header_line(line: str) -> Tuple[str, str]:
    stripped = line.strip()
    match = re.match(r"^([A-Z]\d+\.|\d+\))\s*(.+)$", stripped)
    if match:
        return match.group(1), match.group(2).strip()
    if " " in stripped:
        head, tail = stripped.split(" ", 1)
        return head, tail.strip()
    return stripped, ""


def _finalise_header_audit_entry(
    entry: Dict[str, Any],
    checks: Mapping[str, bool],
) -> Dict[str, Any]:
    score_breakdown = {name: 1.0 if bool(result) else 0.0 for name, result in checks.items()}
    entry["checks"] = {name: bool(result) for name, result in checks.items()}
    entry["score_breakdown"] = score_breakdown
    entry["score_total"] = float(sum(score_breakdown.values()))
    return entry


def _verify_headers(
    candidates: Sequence[Mapping[str, Any]],
    pages: Sequence[PageRecord],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    verified: List[Dict[str, Any]] = []
    discarded: List[Dict[str, Any]] = []
    audits: List[Dict[str, Any]] = []
    for candidate in candidates:
        raw_candidate = dict(candidate)
        try:
            page_num = int(candidate.get("page") or 0)
        except Exception:
            page_num = 0
        label = str(candidate.get("label") or "").strip()
        text = str(candidate.get("text") or "").strip()
        confidence_value_raw = candidate.get("confidence")
        if confidence_value_raw is None:
            confidence_float = 1.0
        else:
            try:
                confidence_float = float(confidence_value_raw)
            except (TypeError, ValueError):  # pragma: no cover - defensive casting
                confidence_float = 1.0
        checks = {
            "page_valid": 1 <= page_num <= len(pages),
            "label_present": bool(label),
            "text_present": bool(text),
            "raw_hit": False,
            "norm_match": False,
            "line_match": False,
        }
        audit_entry: Dict[str, Any] = {
            "label": label,
            "text": text,
            "page": page_num,
            "source": candidate.get("source", "heuristic"),
            "raw_candidate": raw_candidate,
            "checks": {},
            "score_breakdown": {},
            "score_total": 0.0,
            "result": "discarded",
            "confidence": confidence_float,
        }
        if not checks["page_valid"]:
            reason = "invalid_page"
            audit_entry["reason"] = reason
            discarded.append(dict(candidate, reason=reason))
            audits.append(_finalise_header_audit_entry(audit_entry, checks))
            continue
        if not checks["label_present"] or not checks["text_present"]:
            reason = "missing_fields"
            audit_entry["reason"] = reason
            discarded.append(dict(candidate, reason=reason))
            audits.append(_finalise_header_audit_entry(audit_entry, checks))
            continue
        page = pages[page_num - 1]
        search_variants = [f"{label} {text}", f"{label}{text}", f"{label}  {text}"]
        raw_hit: Optional[Tuple[int, int]] = None
        for variant in search_variants:
            idx = page.raw_text.find(variant)
            if idx >= 0:
                raw_hit = (idx, idx + len(variant))
                break
        if raw_hit is not None:
            checks["raw_hit"] = True
        norm_variant = _normalise_text(f"{label} {text}")
        if norm_variant in page.norm_text:
            checks["norm_match"] = True
        if not checks["raw_hit"] and not checks["norm_match"]:
            reason = "not_found"
            audit_entry["reason"] = reason
            discarded.append(dict(candidate, reason=reason))
            audits.append(_finalise_header_audit_entry(audit_entry, checks))
            continue
        line_idx = None
        for idx, line in enumerate(page.lines):
            normalized_line = _normalise_text(line)
            if normalized_line.startswith(_normalise_text(label)):
                line_idx = idx
                break
        if line_idx is not None:
            checks["line_match"] = True
        style = page.line_styles[line_idx] if (line_idx is not None and line_idx < len(page.line_styles)) else {}
        verification = "exact" if raw_hit else "normalized"
        record = {
            "level": candidate.get("level"),
            "label": label,
            "text": text,
            "page": page_num,
            "confidence": confidence_float,
            "span": raw_hit,
            "verification": verification,
            "line_idx": line_idx,
            "style": style,
        }
        verified.append(record)
        audit_entry.update(
            {
                "line_idx": line_idx,
                "span": raw_hit,
                "verification": verification,
                "style": style,
                "result": "verified",
                "confidence": confidence_float,
            }
        )
        audits.append(_finalise_header_audit_entry(audit_entry, checks))
    verified.sort(key=lambda item: (int(item.get("page") or 0), item.get("span", (0, 0))[0]))
    return verified, discarded, audits


def _build_page_headers(headers: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    grouped: MutableMapping[int, List[Dict[str, Any]]] = {}
    for entry in headers:
        page = int(entry.get("page") or 0)
        grouped.setdefault(page, []).append(dict(entry))
    pages: List[Dict[str, Any]] = []
    for page_num in sorted(grouped):
        page_headers = grouped[page_num]
        page_headers.sort(key=lambda item: item.get("line_idx", 0) if item.get("line_idx") is not None else 9999)
        pages.append({"page": page_num, "headers": page_headers})
    return pages


def _build_header_shards(headers: Sequence[Mapping[str, Any]], chunks: Sequence[MicroChunk]) -> List[Dict[str, Any]]:
    by_page: MutableMapping[int, List[MicroChunk]] = {}
    for chunk in chunks:
        page = int(chunk.get("page") or 0)
        by_page.setdefault(page, []).append(chunk)
    for chunk_list in by_page.values():
        chunk_list.sort(key=lambda ch: (ch.get("token_span") or (0, 0))[0])

    shards: List[Dict[str, Any]] = []
    for header in headers:
        page = int(header.get("page") or 0)
        span = header.get("span") or (0, 0)
        chunk_list = by_page.get(page, [])
        chosen: List[MicroChunk] = []
        for chunk in chunk_list:
            char_span = chunk.get("char_span") or (0, 0)
            if char_span and span and char_span[0] >= span[0]:
                chosen.append(chunk)
            if len(chosen) >= 2:
                break
        if not chosen and chunk_list:
            chosen = chunk_list[:2]
        shards.append(
            {
                "label": header.get("label"),
                "text": header.get("text"),
                "page": page,
                "micro_ids": [chunk.get("micro_id") for chunk in chosen if chunk.get("micro_id")],
            }
        )
    return shards


def _run_header_pass(
    ingest: IngestResult,
    chunks: Sequence[MicroChunk],
    *,
    llm_client: Any,
    sidecar_dir: Path,
) -> HeaderResult:
    heuristic_entries = _fallback_headers(ingest.pages)

    llm_verified = VerifiedHeaders()
    llm_rows: List[Dict[str, Any]] = []
    llm_error: Optional[str] = None
    llm_payload: Dict[str, Any] = {}
    if llm_client is not None:
        LOGGER.debug("[UF pipeline] invoking header LLM pass")
        llm_verified, llm_error, llm_rows, llm_payload = _llm_headers(ingest, llm_client)
        if llm_error:
            LOGGER.warning("[UF pipeline] header LLM error: %s", llm_error)
    else:
        LOGGER.debug("[UF pipeline] header LLM client not provided; using heuristics only")

    entries = list(heuristic_entries)
    meta_lookup: Dict[Tuple[int, str], Dict[str, Any]] = {}
    for candidate in heuristic_entries:
        key = (int(candidate.get("page") or 0), str(candidate.get("label") or ""))
        meta_lookup[key] = {
            "source": candidate.get("source", "heuristic"),
            "confidence": candidate.get("confidence"),
        }

    if llm_verified.headers:
        entries.extend(_llm_candidates_from_verified(llm_verified))
        for header in llm_verified.sorted():
            key = (header.page, header.label)
            meta_lookup[key] = {
                "source": header.source or "llm",
                "confidence": header.confidence,
                "span": header.span,
                "verification": header.verification,
            }

    verified, discarded, verification_audit = _verify_headers(entries, ingest.pages)
    for record in verified:
        key = (int(record.get("page") or 0), str(record.get("label") or ""))
        meta = meta_lookup.get(key)
        if meta:
            record["source"] = meta.get("source", record.get("source", "heuristic"))
            if meta.get("confidence") is not None:
                record["confidence"] = float(meta["confidence"])
            span = meta.get("span")
            if span and (not record.get("span") or record.get("span") == (0, 0)):
                record["span"] = tuple(span)
            verification = meta.get("verification")
            if verification:
                record["verification"] = verification
        else:
            record.setdefault("source", "heuristic")

    merged, repairs = aggressive_sequence_repair(
        verified,
        [page.raw_text for page in ingest.pages],
        [page.tokens for page in ingest.pages],
    )
    for repair in repairs:
        repair["source"] = "repair"
    for entry in merged:
        entry.setdefault("source", "heuristic")

    page_headers = _build_page_headers(merged)
    shards = _build_header_shards(merged, chunks)

    header_path = _write_json(sidecar_dir / "uf_pipeline" / "headers.json", merged)
    page_path = _write_json(sidecar_dir / "uf_pipeline" / "headers_by_page.json", page_headers)
    shards_path = _write_json(sidecar_dir / "uf_pipeline" / "header_shards.json", shards)

    artifacts = {
        "headers": header_path,
        "headers_by_page": page_path,
        "header_shards": shards_path,
    }
    if llm_rows:
        llm_path = _write_json(sidecar_dir / "uf_pipeline" / "headers_llm.json", llm_rows)
        artifacts["headers_llm"] = llm_path

    header_audit = {
        "heuristic_candidates": _json_sanitise(heuristic_entries),
        "llm": {
            "error": llm_error,
            "rows": _json_sanitise(llm_rows),
            "payload": llm_payload.get("payload") if llm_payload else None,
            "raw_response": llm_payload.get("raw_response") if llm_payload else None,
        },
        "verification": _json_sanitise(verification_audit),
        "discarded_candidates": _json_sanitise(discarded),
    }

    return HeaderResult(
        headers=merged,
        pages=page_headers,
        repairs=repairs,
        header_shards=shards,
        artifacts=artifacts,
        audit=header_audit,
    )


# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------


_NUMBER_RX = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_UNIT_RX = re.compile(r"\b(?:mm|cm|m|km|in|ft|°c|°f|psi|kpa|bar|hz|rpm|kw|mw|s|ms)\b", re.IGNORECASE)


def _load_table_rows(table: Mapping[str, Any]) -> List[List[str]]:
    csv_path = table.get("csv")
    if not csv_path:
        return []
    try:
        path = Path(csv_path)
        if not path.exists():
            return []
        import csv

        rows: List[List[str]] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            for row in reader:
                rows.append([cell.strip() for cell in row])
        return rows
    except Exception:  # pragma: no cover - defensive
        return []


def _link_tables_to_chunks(tables: Sequence[Mapping[str, Any]], chunks: Sequence[MicroChunk]) -> List[Dict[str, Any]]:
    linked: List[Dict[str, Any]] = []
    for table in tables:
        rows = _load_table_rows(table)
        text_blobs = " \n".join(" ".join(row) for row in rows if row)
        numbers = sorted({match.group(0) for match in _NUMBER_RX.finditer(text_blobs)}) if text_blobs else []
        units = sorted({match.group(0).lower() for match in _UNIT_RX.finditer(text_blobs)}) if text_blobs else []
        supporters: List[str] = []
        for chunk in chunks:
            lex = chunk.get("lex") or {}
            chunk_numbers = set(lex.get("numbers") or [])
            chunk_units = set(lex.get("units") or [])
            if chunk_numbers.intersection(numbers) or chunk_units.intersection(units):
                micro_id = chunk.get("micro_id")
                if micro_id:
                    supporters.append(micro_id)
        linked.append(
            {
                "page": table.get("page"),
                "index": table.get("index"),
                "csv": table.get("csv"),
                "rows": rows,
                "numbers": numbers,
                "units": units,
                "parameter_supports": supporters,
            }
        )
    return linked


# ---------------------------------------------------------------------------
# Retrieval helpers
# ---------------------------------------------------------------------------


def _build_retrieval(
    chunks: Sequence[MicroChunk],
    shards: Sequence[Mapping[str, Any]],
    tables: Sequence[Mapping[str, Any]],
    spans: Sequence[Mapping[str, Any]],
    *,
    sidecar_dir: Path,
) -> RetrievalSummary:
    idx_dir = sidecar_dir / "uf_pipeline" / "indexes"
    micro_bm25 = BM25Store(idx_dir / "micro_bm25.pkl")
    micro_embeddings = EmbeddingStore(idx_dir / "micro_embeddings.parquet")
    micro_bm25.build(chunks)
    micro_embeddings.build(chunks)

    chunk_by_id: Dict[str, MicroChunk] = {}
    for chunk in chunks:
        micro_id = chunk.get("micro_id")
        if isinstance(micro_id, str):
            chunk_by_id[micro_id] = chunk

    header_docs: List[Dict[str, Any]] = []
    for idx, shard in enumerate(shards):
        label = str(shard.get("label") or "").strip()
        text = str(shard.get("text") or "").strip()
        page = shard.get("page")
        header_id = f"header-{idx:03d}-p{page}" if page else f"header-{idx:03d}"
        snippet_parts: List[str] = []
        for micro_id in shard.get("micro_ids") or []:
            chunk = chunk_by_id.get(str(micro_id))
            if not chunk:
                continue
            snippet = str(chunk.get("text") or "").strip()
            if snippet:
                snippet_parts.append(snippet)
            if len(snippet_parts) >= 2:
                break
        content_parts = [f"{label} {text}".strip()]
        if snippet_parts:
            content_parts.append(" ".join(snippet_parts))
        content = _normalise_text(" ".join(part for part in content_parts if part))
        header_docs.append(
            {
                "micro_id": header_id,
                "doc_id": chunk_by_id.get(str((shard.get("micro_ids") or [None])[0]), {}).get("doc_id")
                or shard.get("doc_id")
                or "header",
                "text": content,
                "norm_text": content,
                "label": label,
                "page": page,
                "micro_ids": [str(mid) for mid in shard.get("micro_ids") or []],
                "shard": dict(shard),
            }
        )

    table_docs: List[Dict[str, Any]] = []
    for table in tables:
        page = table.get("page")
        index = table.get("index")
        table_id = (
            f"table-{page}-{index}"
            if page is not None and index is not None
            else f"table-{len(table_docs):03d}"
        )
        rows = table.get("rows") or []
        row_texts: List[str] = []
        for row in rows:
            if not isinstance(row, (list, tuple)):
                continue
            row_text = " ".join(str(cell or "").strip() for cell in row if cell)
            if row_text:
                row_texts.append(row_text)
        numbers = " ".join(table.get("numbers") or [])
        units = " ".join(table.get("units") or [])
        description = " ".join(
            part for part in (table.get("title"), table.get("summary")) if part
        )
        content = _normalise_text(" ".join(row_texts + [numbers, units, description]))
        table_docs.append(
            {
                "micro_id": table_id,
                "doc_id": table.get("doc_id") or "table",
                "text": content,
                "norm_text": content,
                "page": page,
                "index": index,
                "parameter_supports": [str(mid) for mid in table.get("parameter_supports") or []],
                "table": dict(table),
            }
        )

    header_bm25: Optional[BM25Store] = None
    header_embeddings: Optional[EmbeddingStore] = None
    if header_docs:
        header_bm25 = BM25Store(idx_dir / "header_bm25.pkl")
        header_embeddings = EmbeddingStore(idx_dir / "header_embeddings.parquet")
        header_bm25.build(header_docs)
        header_embeddings.build(header_docs)

    table_bm25: Optional[BM25Store] = None
    table_embeddings: Optional[EmbeddingStore] = None
    if table_docs:
        table_bm25 = BM25Store(idx_dir / "table_bm25.pkl")
        table_embeddings = EmbeddingStore(idx_dir / "table_embeddings.parquet")
        table_bm25.build(table_docs)
        table_embeddings.build(table_docs)

    span_map: Dict[str, Dict[str, Any]] = {}
    span_records: List[Dict[str, Any]] = []
    for span_index, span in enumerate(spans):
        chunk_indices = span.get("chunk_indices") or []
        for idx_in_span in chunk_indices:
            try:
                chunk = chunks[int(idx_in_span)]
            except (IndexError, ValueError, TypeError):
                continue
            micro_id = chunk.get("micro_id")
            if not micro_id:
                continue
            score = float(span.get("score") or 0.0)
            existing = span_map.get(micro_id)
            if existing and existing.get("score", 0.0) >= score:
                continue
            entry = {
                "micro_id": micro_id,
                "span_id": span_index,
                "score": score,
                "start_index": span.get("start_index"),
                "end_index": span.get("end_index"),
                "E": span.get("E"),
                "F": span.get("F"),
                "H": span.get("H"),
                "G_penalty": span.get("G_penalty"),
            }
            span_map[micro_id] = entry
    span_records.extend(span_map.values())

    header_doc_path = _write_json(sidecar_dir / "uf_pipeline" / "header_docs.json", header_docs)
    table_doc_path = _write_json(sidecar_dir / "uf_pipeline" / "table_docs.json", table_docs)
    span_index_path: Optional[Path] = None
    if header_cfg.HEADER_MODE != "preprocess_only" and span_records:
        span_index_path = _write_json(
            sidecar_dir / "uf_pipeline" / "efhg_span_index.json",
            span_records,
        )

    return RetrievalSummary(
        micro_index_size=len(chunks),
        header_shard_count=sum(1 for shard in shards if shard.get("micro_ids")),
        table_count=len(tables),
        bm25_path=micro_bm25.path if micro_bm25.path.exists() else None,
        embedding_path=micro_embeddings.path if micro_embeddings.path.exists() else None,
        header_bm25_path=header_bm25.path if header_bm25 and header_bm25.path.exists() else None,
        header_embedding_path=header_embeddings.path if header_embeddings and header_embeddings.path.exists() else None,
        table_bm25_path=table_bm25.path if table_bm25 and table_bm25.path.exists() else None,
        table_embedding_path=table_embeddings.path if table_embeddings and table_embeddings.path.exists() else None,
        span_index_path=span_index_path if span_records else None,
        header_doc_path=header_doc_path if header_docs else None,
        table_doc_path=table_doc_path if table_docs else None,
    )


# ---------------------------------------------------------------------------
# EFHG audit helpers
# ---------------------------------------------------------------------------


def _write_chunk_audit(
    sidecar_dir: Path,
    chunks: Sequence[MicroChunk],
    scores: Sequence[Mapping[str, Any]],
    spans: Sequence[Mapping[str, Any]],
) -> Dict[str, Path]:
    audit_dir = sidecar_dir / "uf_pipeline"
    if header_cfg.HEADER_MODE == "preprocess_only":
        return {}

    neighbor_info = compute_fluid_neighbors(chunks)
    chunk_rows = []
    for idx, (chunk, score) in enumerate(zip(chunks, scores)):
        row = {
            "micro_id": chunk.get("micro_id"),
            "page": chunk.get("page"),
            "token_count": chunk.get("token_count"),
            "S_start": score.get("S_start"),
            "S_stop": score.get("S_stop"),
            "entropy": score.get("entropy"),
            "modalness": score.get("modalness"),
            "header_weight": score.get("header_weight"),
            "stop_punct": score.get("stop_punct"),
        }
        neighbor = neighbor_info[idx] if idx < len(neighbor_info) else {}
        if neighbor.get("prev"):
            row["fluid_prev"] = neighbor["prev"]
        if neighbor.get("next"):
            row["fluid_next"] = neighbor["next"]
        chunk_rows.append(row)
    scores_path = _write_jsonl(audit_dir / "uf_scores.jsonl", chunk_rows)
    spans_path = _write_json(audit_dir / "uf_spans.json", list(spans))
    chunk_records = []
    for chunk in chunks:
        chunk_records.append(
            {
                "micro_id": chunk.get("micro_id"),
                "page": chunk.get("page"),
                "pages": chunk.get("pages"),
                "token_span": chunk.get("token_span"),
                "char_span": chunk.get("char_span"),
                "text": chunk.get("text"),
                "norm_text": chunk.get("norm_text"),
                "style": chunk.get("style"),
                "lex": chunk.get("lex"),
                "emb": chunk.get("emb"),
                "domain_hint": chunk.get("domain_hint"),
                "section_id": chunk.get("section_id"),
                "section_title": chunk.get("section_title"),
                "header_anchor": chunk.get("header_anchor"),
            }
        )
    chunks_path = _write_jsonl(audit_dir / "uf_chunks.jsonl", chunk_records)
    return {
        "uf_scores": scores_path,
        "uf_spans": spans_path,
        "uf_chunks": chunks_path,
    }


# ---------------------------------------------------------------------------
# Public pipeline entry point
# ---------------------------------------------------------------------------


def run_pipeline(
    pdf_path: str,
    *,
    doc_id: str,
    session_id: Optional[str] = None,
    sidecar_dir: Optional[str | os.PathLike[str]] = None,
    llm_client: Any = None,
    pre_extracted: Optional[Mapping[str, Any]] = None,
) -> PipelineResult:
    """Execute the ultrafine pipeline for ``pdf_path``.

    Parameters
    ----------
    pdf_path:
        The source PDF file.
    doc_id:
        Identifier used when emitting artefacts and microchunk metadata.
    session_id:
        Optional session identifier to segregate artefacts.
    sidecar_dir:
        Base directory for generated artefacts.  Defaults to ``sidecars/<session>``
        when a session id is provided, otherwise ``sidecars/<doc_id>``.
    llm_client:
        Optional chat-completion client used for the header pass.  When ``None``
        the module falls back to deterministic header detection heuristics.
    pre_extracted:
        Optional extraction payload (matching the structure returned by
        :func:`backend.ingest.pdf_extract.extract`) to avoid duplicate work.
    """

    base_dir = Path(sidecar_dir) if sidecar_dir else Path("sidecars")
    target_dir = base_dir / (session_id or doc_id or "document")
    target_dir.mkdir(parents=True, exist_ok=True)

    ingest = _ingest_pdf(pdf_path, doc_id=doc_id, sidecar_dir=target_dir, pre_extracted=pre_extracted)
    chunks = microchunk_text(ingest.parts, size=90, overlap=12, boundary_align=True)
    for idx, chunk in enumerate(chunks):
        chunk.setdefault("sequence_index", idx)
        chunk.setdefault("doc_id", doc_id)

    chunk_scores = compute_chunk_scores(chunks)
    spans: List[Dict[str, Any]] = []
    if header_cfg.HEADER_MODE != "preprocess_only":
        spans = run_efhg(chunks)
    header_result = _run_header_pass(ingest, chunks, llm_client=llm_client, sidecar_dir=target_dir)
    table_records = _link_tables_to_chunks(ingest.tables, chunks)
    tables_path = _write_json(target_dir / "uf_pipeline" / "tables.json", table_records)
    retrieval_summary = _build_retrieval(
        chunks,
        header_result.header_shards,
        table_records,
        spans,
        sidecar_dir=target_dir,
    )
    chunk_artifacts = _write_chunk_audit(target_dir, chunks, chunk_scores, spans)

    artifacts: Dict[str, Path] = {
        **ingest.page_artifacts,
        **header_result.artifacts,
        "tables": tables_path,
        **chunk_artifacts,
    }
    if retrieval_summary.header_doc_path:
        artifacts["header_docs"] = retrieval_summary.header_doc_path
    if retrieval_summary.table_doc_path:
        artifacts["table_docs"] = retrieval_summary.table_doc_path
    if retrieval_summary.span_index_path:
        artifacts["efhg_span_index"] = retrieval_summary.span_index_path
    audits = {
        "headers": header_result.audit,
        "tables": table_records,
    }

    return PipelineResult(
        uf_chunks=list(chunks),
        chunk_scores=list(chunk_scores),
        efhg_spans=list(spans),
        headers=header_result,
        tables=table_records,
        retrieval=retrieval_summary,
        artifacts=artifacts,
        audits=audits,
    )


def prepare_pass_chunk(
    chunk: MicroChunk,
    *,
    document: str,
    position: Optional[int] = None,
    default_section: str = "Document",
) -> Dict[str, Any]:
    """Return a chunk dictionary formatted for downstream passes.

    The helper normalises pagination, section metadata, and ensures a ``meta``
    container is present.  It intentionally preserves any existing metadata on
    the source chunk while layering the UF-pipeline specific flags expected by
    the discipline passes.
    """

    enriched: Dict[str, Any] = dict(chunk)

    micro_id = enriched.get("micro_id") or enriched.get("chunk_id")
    if micro_id:
        enriched["chunk_id"] = str(micro_id)

    enriched["document"] = document or "Document"
    pages = enriched.get("pages")
    page_start = page_end = None
    if isinstance(pages, list) and pages:
        try:
            page_start = int(pages[0])
            page_end = int(pages[-1])
        except Exception:
            page_start = page_end = None
    if page_start is None:
        page_value = enriched.get("page")
        try:
            page_start = int(page_value) if page_value is not None else 1
        except Exception:
            page_start = 1
        try:
            page_end = int(enriched.get("page_end") or page_start)
        except Exception:
            page_end = page_start
        enriched.setdefault("pages", [page_start])
    enriched["page_start"] = page_start
    enriched["page_end"] = page_end if page_end is not None else page_start

    section_number = enriched.get("section_number") or enriched.get("section_id") or ""
    section_title = (
        enriched.get("section_title")
        or enriched.get("section_name")
        or default_section
    )
    enriched["section_number"] = str(section_number) if section_number is not None else ""
    enriched["section_title"] = section_title
    enriched["section_name"] = section_title

    sequence_index = enriched.get("sequence_index")
    try:
        sequence_index_int = int(sequence_index)
    except Exception:
        sequence_index_int = None
    if sequence_index_int is None and position is not None:
        sequence_index_int = int(position)
    enriched["chunk_index_in_section"] = sequence_index_int or 0

    meta = dict(enriched.get("meta") or {})
    meta.setdefault("uf_pipeline", True)
    enriched["meta"] = meta
    enriched.setdefault("chunk_type", "uf")

    return enriched


__all__ = ["PipelineResult", "prepare_pass_chunk", "run_pipeline"]

