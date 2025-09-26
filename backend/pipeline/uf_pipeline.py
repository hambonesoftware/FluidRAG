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
import inspect
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

import regex as re

from chunking.efhg import compute_chunk_scores, compute_fluid_neighbors, run_efhg
from ingest.microchunker import MicroChunk, microchunk_text

from ..ingest.pdf_extract import extract as pdf_extract
from ..parse.header_sequence_repair import aggressive_sequence_repair
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
        styles = page_styles[page_idx - 1] if page_idx - 1 < len(page_styles) else [{} for _ in lines]
        joined = "\n".join(lines)
        norm = _normalise_text(joined)
        offsets: List[int] = []
        tokens: List[Dict[str, Any]] = []
        cursor = 0
        line_entries: List[Dict[str, Any]] = []
        for line_idx, line in enumerate(lines):
            style = styles[line_idx] if line_idx < len(styles) else {}
            offsets.append(cursor)
            line_tokens = _tokenise_with_offsets(line, base_offset=cursor)
            tokens.extend({**token, "line_idx": line_idx} for token in line_tokens)
            line_entries.append(
                {
                    "index": line_idx,
                    "text": line,
                    "norm_text": _normalise_text(line),
                    "style": style,
                    "tokens": line_tokens,
                    "break_reason": "line_break",
                }
            )
            indent = None
            bbox = style.get("bbox") if isinstance(style, Mapping) else None
            if isinstance(bbox, (list, tuple)) and len(bbox) >= 1:
                try:
                    indent = float(bbox[0])
                except Exception:  # pragma: no cover - defensive
                    indent = None
            part = {
                "doc_id": doc_id,
                "text": line,
                "page": page_idx,
                "line_idx": line_idx,
                "font_size": style.get("font_size"),
                "font_weight": style.get("font_weight"),
                "bold": style.get("bold"),
                "indent": indent,
                "break_reason": "line_break",
                "header_anchor": bool(_HEADER_MARK_RX.match(line.strip())),
            }
            parts.append(part)
            cursor += len(line) + 1

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
                line_styles=[dict(style) for style in styles],
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


HEADER_USER_PROMPT = (
    "List every section and subsection header in the document. Include numbered "
    "clauses (e.g. `1)`), appendix headers (`A1.` etc.) and any roman numeral "
    "sections. Return one ```json fenced object with an array named `headers`. "
    "Each header entry must provide: level (int), label (string), text (string), "
    "page (1-indexed int), confidence (0-1 float). No additional prose."
)


def _call_llm(llm_client: Any, messages: List[Dict[str, str]], *, temperature: float = 0.0, max_tokens: int = 1024) -> Optional[Any]:
    if llm_client is None:
        return None
    chat = getattr(llm_client, "chat", None)
    if chat is None:
        raise TypeError("llm_client must expose a chat(messages, **kwargs) method")
    result = chat(messages, temperature=temperature, max_tokens=max_tokens)
    if inspect.isawaitable(result):  # pragma: no cover - exercised in integration
        return asyncio.run(result)
    return result


def _extract_json_payload(response: Any) -> Optional[Any]:
    if response is None:
        return None
    if isinstance(response, Mapping):
        for key in ("json", "data", "payload", "text"):
            if key in response and response[key]:
                candidate = response[key]
                if isinstance(candidate, str):
                    return _extract_json_payload(candidate)
                return candidate
        return response
    if isinstance(response, str):
        fenced = re.search(r"```json\s*(\{.*?\})\s*```", response, flags=re.DOTALL)
        text = fenced.group(1) if fenced else response
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    return None


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
                }
            )
    return headers


def _split_header_line(line: str) -> Tuple[str, str]:
    stripped = line.strip()
    match = re.match(r"^([A-Z]\d+\.|\d+\))\s*(.+)$", stripped)
    if match:
        return match.group(1), match.group(2).strip()
    if " " in stripped:
        head, tail = stripped.split(" ", 1)
        return head, tail.strip()
    return stripped, ""


def _verify_headers(
    candidates: Sequence[Mapping[str, Any]],
    pages: Sequence[PageRecord],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    verified: List[Dict[str, Any]] = []
    discarded: List[Dict[str, Any]] = []
    for candidate in candidates:
        try:
            page_num = int(candidate.get("page") or 0)
        except Exception:
            page_num = 0
        if page_num <= 0 or page_num > len(pages):
            discarded.append(dict(candidate, reason="invalid_page"))
            continue
        page = pages[page_num - 1]
        label = str(candidate.get("label") or "").strip()
        text = str(candidate.get("text") or "").strip()
        if not label or not text:
            discarded.append(dict(candidate, reason="missing_fields"))
            continue
        search_variants = [f"{label} {text}", f"{label}{text}", f"{label}  {text}"]
        raw_hit: Optional[Tuple[int, int]] = None
        for variant in search_variants:
            idx = page.raw_text.find(variant)
            if idx >= 0:
                raw_hit = (idx, idx + len(variant))
                break
        verification = "exact" if raw_hit else "normalized"
        if raw_hit is None:
            norm_variant = _normalise_text(f"{label} {text}")
            if norm_variant not in page.norm_text:
                discarded.append(dict(candidate, reason="not_found"))
                continue
        line_idx = None
        for idx, line in enumerate(page.lines):
            normalized_line = _normalise_text(line)
            if normalized_line.startswith(_normalise_text(label)):
                line_idx = idx
                break
        style = page.line_styles[line_idx] if (line_idx is not None and line_idx < len(page.line_styles)) else {}
        record = {
            "level": candidate.get("level"),
            "label": label,
            "text": text,
            "page": page_num,
            "confidence": float(candidate.get("confidence", 1.0)),
            "span": raw_hit,
            "verification": verification,
            "line_idx": line_idx,
            "style": style,
        }
        verified.append(record)
    verified.sort(key=lambda item: (int(item.get("page") or 0), item.get("span", (0, 0))[0]))
    return verified, discarded


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
    pages_text = []
    for page in ingest.pages:
        pages_text.append(f"=== PAGE {page.page_number} ===\n{page.norm_text}")
    prompt = "\n\n".join(pages_text)
    messages = [
        {"role": "system", "content": "You extract structured headers from PDFs."},
        {"role": "user", "content": HEADER_USER_PROMPT + "\n\n" + prompt},
    ]
    response = _call_llm(llm_client, messages, temperature=0.0, max_tokens=1200)
    payload = _extract_json_payload(response)
    entries: List[Dict[str, Any]] = []
    if isinstance(payload, Mapping) and "headers" in payload:
        headers = payload.get("headers")
        if isinstance(headers, list):
            entries = [dict(item) for item in headers if isinstance(item, Mapping)]
    elif isinstance(payload, list):
        entries = [dict(item) for item in payload if isinstance(item, Mapping)]

    if not entries:
        LOGGER.debug("[UF pipeline] LLM header pass returned no entries, using fallback heuristics")
        entries = _fallback_headers(ingest.pages)

    verified, discarded = _verify_headers(entries, ingest.pages)
    merged, repairs = aggressive_sequence_repair(
        verified,
        [page.raw_text for page in ingest.pages],
        [page.tokens for page in ingest.pages],
    )
    page_headers = _build_page_headers(merged)
    shards = _build_header_shards(merged, chunks)

    header_path = _write_json(sidecar_dir / "uf_pipeline" / "headers.json", merged)
    page_path = _write_json(sidecar_dir / "uf_pipeline" / "headers_by_page.json", page_headers)
    shards_path = _write_json(sidecar_dir / "uf_pipeline" / "header_shards.json", shards)

    audit_payload = {
        "llm_response": payload,
        "discarded": discarded,
        "repairs": repairs,
        "prompt_char_length": len(prompt),
    }
    audit_path = _write_json(sidecar_dir / "uf_pipeline" / "header_audit.json", audit_payload)

    artifacts = {
        "headers": header_path,
        "headers_by_page": page_path,
        "header_shards": shards_path,
        "header_audit": audit_path,
    }
    return HeaderResult(
        headers=merged,
        pages=page_headers,
        repairs=repairs,
        header_shards=shards,
        artifacts=artifacts,
        audit=audit_payload,
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
    *,
    sidecar_dir: Path,
) -> RetrievalSummary:
    idx_dir = sidecar_dir / "uf_pipeline" / "indexes"
    bm25_store = BM25Store(idx_dir / "bm25.pkl")
    embedding_store = EmbeddingStore(idx_dir / "embeddings.parquet")
    bm25_store.build(chunks)
    embedding_store.build(chunks)
    return RetrievalSummary(
        micro_index_size=len(chunks),
        header_shard_count=sum(1 for shard in shards if shard.get("micro_ids")),
        table_count=len(tables),
        bm25_path=bm25_store.path if bm25_store.path.exists() else None,
        embedding_path=embedding_store.path if embedding_store.path.exists() else None,
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
    spans = run_efhg(chunks)
    header_result = _run_header_pass(ingest, chunks, llm_client=llm_client, sidecar_dir=target_dir)
    table_records = _link_tables_to_chunks(ingest.tables, chunks)
    tables_path = _write_json(target_dir / "uf_pipeline" / "tables.json", table_records)
    retrieval_summary = _build_retrieval(chunks, header_result.header_shards, table_records, sidecar_dir=target_dir)
    chunk_artifacts = _write_chunk_audit(target_dir, chunks, chunk_scores, spans)

    artifacts: Dict[str, Path] = {
        **ingest.page_artifacts,
        **header_result.artifacts,
        "tables": tables_path,
        **chunk_artifacts,
    }
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

