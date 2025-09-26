"""Chunk preparation helpers for the pass pipeline."""
from __future__ import annotations

import json
import logging
import os
import re

from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple


from backend.persistence import get_preprocess_cache

from backend.prompts import PASS_PROMPTS, atomic_user_template
from backend.state import get_state
from backend.utils.strings import s

from backend.domain import PASS_DOMAIN_LEXICON, PASS_DOMAIN_THRESHOLD

from chunking.efhg import compute_chunk_scores, run_efhg

from ..uf_pipeline import prepare_pass_chunk, run_pipeline as run_uf_pipeline
from .constants import CHUNK_GROUP_TOKEN_LIMIT

log = logging.getLogger("FluidRAG.chunking")


def _normalize_for_json(value: Any) -> Any:
    """Best-effort conversion of chunk fields for JSON serialization."""

    if isinstance(value, dict):
        return {str(key): _normalize_for_json(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_normalize_for_json(item) for item in value]
    if isinstance(value, tuple) or isinstance(value, set):
        return [_normalize_for_json(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:  # pragma: no cover - defensive
            pass
    try:
        return float(value)
    except Exception:  # pragma: no cover - defensive
        pass
    try:
        return str(value)
    except Exception:  # pragma: no cover - defensive
        return repr(value)


def _collect_headers(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Summarize unique headers from the supplied chunks."""

    headers: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for chunk in chunks:
        section_number = s(chunk.get("section_number"))
        section_name = s(chunk.get("section_name"))
        key = (section_number, section_name)
        existing = headers.get(key)
        page_start = chunk.get("page_start") or chunk.get("page") or 1
        page_end = chunk.get("page_end") or chunk.get("page") or page_start
        if existing is None:
            headers[key] = {
                "section_number": section_number,
                "section_name": section_name,
                "document": s(chunk.get("document")) or "Document",
                "page_start": page_start,
                "page_end": page_end,
            }
        else:
            existing["page_start"] = min(existing.get("page_start", page_start), page_start)
            existing["page_end"] = max(existing.get("page_end", page_end), page_end)
    return list(headers.values())


def _normalize_for_lookup(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip().lower()


def _build_section_lookup(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    lookup: List[Dict[str, Any]] = []
    for idx, chunk in enumerate(chunks):
        text = s(chunk.get("text"))
        section_number = s(chunk.get("section_number") or chunk.get("section_id"))
        section_name = s(chunk.get("section_name") or chunk.get("section_title"))
        lookup.append(
            {
                "chunk_index": idx,
                "section_number": section_number,
                "section_name": section_name,
                "text": text,
                "normalized_text": _normalize_for_lookup(text),
            }
        )
    return lookup


def _compute_domain_scores(chunk: Dict[str, Any]) -> Dict[str, int]:
    meta = chunk.setdefault("meta", {})
    existing = meta.get("domain_scores")
    if isinstance(existing, dict):
        return existing
    text_parts = [
        s(chunk.get("section_name") or chunk.get("section_title")),
        s(chunk.get("section_number") or chunk.get("section_id")),
        s(chunk.get("text")),
    ]
    normalized = _normalize_for_lookup(" ".join(part for part in text_parts if part))
    scores: Dict[str, int] = {}
    for pass_name, keywords in PASS_DOMAIN_LEXICON.items():
        count = 0
        for keyword in keywords:
            key = keyword.lower().strip()
            if key and key in normalized:
                count += 1
        scores[pass_name] = count
    meta["domain_scores"] = scores
    return scores


def _filter_chunks_for_pass(chunks: List[Dict[str, Any]], pass_name: str) -> List[Dict[str, Any]]:
    threshold = PASS_DOMAIN_THRESHOLD.get(pass_name, 0)
    filtered: List[Dict[str, Any]] = []
    for chunk in chunks:
        scores = _compute_domain_scores(chunk)
        if scores.get(pass_name, 0) >= threshold:
            filtered.append(chunk)
    if not filtered:
        return list(chunks)
    return filtered

def _normalize_stage_payload(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize chunk snapshots for JSON export."""

    normalized_chunks = [_normalize_for_json(dict(chunk)) for chunk in chunks]
    return {
        "chunk_count": len(normalized_chunks),
        "headers": _collect_headers(chunks),
        "chunks": normalized_chunks,
    }


def export_pass_stage_snapshots(
    session_id: str,
    pass_names: Sequence[str],
    include_header: bool = False,
    *,
    output_dir: Optional[str] = None,
) -> None:
    """Write combined stage snapshots for each requested pass."""

    state = get_state(session_id)
    if state is None:
        log.warning("[chunking] export requested for unknown session %s", session_id)
        return

    stage_snapshots = getattr(state, "chunk_stage_snapshots", None)
    if not stage_snapshots:
        log.info("[chunking] no stage snapshots available for session %s", session_id)
        return

    targets = list(dict.fromkeys(pass_names))
    if include_header:
        targets = ["Header", *targets]

    if not targets:
        return

    base_dir = output_dir or os.path.join("backend", "stages")
    try:
        os.makedirs(base_dir, exist_ok=True)
    except Exception:  # pragma: no cover - defensive
        log.exception("[chunking] failed to ensure stage export directory %s", base_dir)
        return

    now = datetime.now(UTC)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    generated_at = now.isoformat().replace("+00:00", "Z")
    normalized_stages = {
        stage: _normalize_stage_payload(list(chunks))
        for stage, chunks in stage_snapshots.items()
    }

    for pass_name in targets:
        safe_name = "_".join(pass_name.split()) or "pass"
        path = os.path.join(base_dir, f"{safe_name}_{timestamp}.json")
        payload = {
            "session_id": session_id,
            "pass": pass_name,
            "generated_at": generated_at,
            "passes": sorted(PASS_PROMPTS.keys()),
            "stages": normalized_stages,
        }
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            log.info(
                "[chunking] wrote pass stage snapshot for %s to %s",
                pass_name,
                path,
            )
        except Exception:  # pragma: no cover - defensive
            log.exception(
                "[chunking] failed to write pass stage snapshot for %s", pass_name
            )


try:  # pragma: no cover - compatibility shim
    from ..preprocess import approximate_tokens  # type: ignore[import]
except Exception:  # pragma: no cover - compatibility shim

    def approximate_tokens(text: str) -> int:
        """Fallback token approximation if preprocess helpers are unavailable."""

        if not text:
            return 0
        return max(1, len(text) // 4)


def ensure_chunks(session_id: str) -> List[Dict[str, Any]]:
    """Load UF chunks for ``session_id`` and enrich them with EFHG metadata."""

    state = get_state(session_id)
    if state is None:
        raise ValueError("Unknown session; upload and preprocess the document first.")

    sidecar_dir = os.path.join("sidecars", session_id)
    try:
        os.makedirs(sidecar_dir, exist_ok=True)
    except Exception:  # pragma: no cover - defensive
        log.exception("[chunking] failed to ensure sidecar directory %s", sidecar_dir)

    document_name = getattr(state, "filename", None) or "Document"
    file_hash = getattr(state, "file_hash", None)

    def _normalise_chunks(source: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for idx, entry in enumerate(source):
            normalized.append(prepare_pass_chunk(entry, document=document_name, position=idx))
        return normalized

    chunks: List[Dict[str, Any]] = []

    if getattr(state, "uf_chunks", None):
        chunks = _normalise_chunks(state.uf_chunks)
    else:
        cached_pre = get_preprocess_cache(file_hash)
        if cached_pre:
            payload = (
                cached_pre.get("micro_chunks")
                or cached_pre.get("macro_chunks")
                or cached_pre.get("chunks")
                or []
            )
            chunks = _normalise_chunks(payload)
            response_payload = cached_pre.get("response") or {}
            uf_summary = response_payload.get("uf_pipeline") or cached_pre.get("uf_pipeline")
            if isinstance(uf_summary, dict):
                state.uf_pipeline = uf_summary
            tables_payload = response_payload.get("tables") or cached_pre.get("tables")
            if isinstance(tables_payload, list):
                state.uf_tables = tables_payload
            headers_payload = response_payload.get("headers") or cached_pre.get("headers")
            if isinstance(headers_payload, list):
                state.headers = headers_payload
            debug_payload = cached_pre.get("debug")
            if isinstance(debug_payload, dict):
                state.debug = dict(debug_payload)
        else:
            pdf_path = getattr(state, "file_path", None)
            if not pdf_path or not os.path.exists(pdf_path):
                uploads_dir = os.getenv("UPLOAD_FOLDER", "uploads")
                pdf_path = os.path.join(uploads_dir, f"{session_id}.pdf")
            doc_id = os.path.splitext(os.path.basename(pdf_path or ""))[0] or session_id or "document"
            uf_result = run_uf_pipeline(
                pdf_path,
                doc_id=doc_id,
                session_id=session_id,
                sidecar_dir=sidecar_dir,
                llm_client=None,
            )
            chunks = [
                prepare_pass_chunk(chunk, document=document_name, position=idx)
                for idx, chunk in enumerate(uf_result.uf_chunks)
            ]
            state.uf_pipeline = uf_result.summary()
            state.uf_tables = uf_result.tables
            state.headers = uf_result.headers.pages

    if not chunks:
        log.warning("[chunking] UF chunk list is empty for session %s", session_id)
        state.uf_chunks = []
        state.standard_section_lookup = {}
        state.chunk_stage_snapshots = {"uf_chunks": [], "uf_scored": [], "efhg_spans": []}
        return []

    scores = compute_chunk_scores(chunks)
    spans = run_efhg(chunks)

    span_membership: Dict[int, List[Dict[str, Any]]] = {}
    for span in spans:
        try:
            start = int(span.get("start_index", -1))
            end = int(span.get("end_index", -1))
        except Exception:
            continue
        for idx in range(start, end + 1):
            entry = {k: span.get(k) for k in ("score", "start_index", "end_index", "preview")}
            entry["span_index"] = spans.index(span)
            span_membership.setdefault(idx, []).append(entry)

    for idx, (chunk, metrics) in enumerate(zip(chunks, scores)):
        meta = dict(chunk.get("meta") or {})
        meta["uf_scores"] = metrics
        members = span_membership.get(idx, [])
        if members:
            best = max(members, key=lambda entry: entry.get("score") or 0.0)
            meta["efhg_span"] = best
            meta["efhg_span_memberships"] = members
        chunk["meta"] = meta

    span_snapshot: List[Dict[str, Any]] = []
    for span in spans:
        record = dict(span)
        members: List[str] = []
        try:
            start = int(span.get("start_index", -1))
            end = int(span.get("end_index", -1))
        except Exception:
            start = end = -1
        for idx in range(start, end + 1):
            if 0 <= idx < len(chunks):
                micro_id = chunks[idx].get("micro_id") or chunks[idx].get("chunk_id")
                if micro_id:
                    members.append(str(micro_id))
        record["micro_ids"] = members
        span_snapshot.append(record)

    raw_snapshot = [dict(chunk) for chunk in chunks]
    scored_snapshot = []
    for chunk in chunks:
        score_meta = chunk.get("meta", {}).get("uf_scores", {})
        scored_snapshot.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "section_number": chunk.get("section_number"),
                "section_name": chunk.get("section_name"),
                "page_start": chunk.get("page_start"),
                "page_end": chunk.get("page_end"),
                "meta": {
                    "uf_scores": score_meta,
                    "efhg_span": chunk.get("meta", {}).get("efhg_span"),
                },
                "text": chunk.get("text"),
            }
        )

    state.uf_chunks = [dict(chunk) for chunk in chunks]
    state.pre_chunks = [dict(chunk) for chunk in chunks]
    state.refined_chunks = list(state.uf_chunks)
    state.clustered_chunks = list(state.uf_chunks)
    state.chunk_stage_snapshots = {
        "uf_chunks": raw_snapshot,
        "uf_scored": scored_snapshot,
        "efhg_spans": span_snapshot,
        "raw_chunking": raw_snapshot,
        "standard_chunks": scored_snapshot,
        "fluid_chunks": scored_snapshot,
        "hep_chunks": scored_snapshot,
    }
    try:
        state.standard_section_lookup = _build_section_lookup(raw_snapshot)
    except Exception:  # pragma: no cover - defensive
        log.exception("[chunking] failed to build section lookup for session %s", session_id)
        state.standard_section_lookup = {}
    return chunks


def chunk_token_len(chunk: Dict[str, Any]) -> int:
    """Estimate the token length for a chunk."""

    return approximate_tokens(chunk.get("text") or "")


def build_groups(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group chunks while respecting the token budget."""

    groups: List[Dict[str, Any]] = []
    current: List[Dict[str, Any]] = []
    current_tokens = 0
    for chunk in chunks:
        tokens = max(1, chunk_token_len(chunk))
        if current and current_tokens + tokens > CHUNK_GROUP_TOKEN_LIMIT:
            groups.append({
                "chunks": current,
                "token_estimate": current_tokens,
            })
            current = []
            current_tokens = 0
        current.append(chunk)
        current_tokens += tokens
    if current:
        groups.append({
            "chunks": current,
            "token_estimate": current_tokens,
        })
    return groups


def build_pass_groups(
    chunks: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """Return default chunk groups and discipline-filtered groups."""

    base_groups = build_groups(chunks)
    per_pass: Dict[str, List[Dict[str, Any]]] = {}
    for pass_name in PASS_DOMAIN_LEXICON:
        filtered = _filter_chunks_for_pass(chunks, pass_name)
        per_pass[pass_name] = build_groups(filtered)
    return base_groups, per_pass


def build_user_prompt(metadata: Dict[str, Any], group: Dict[str, Any], batch_index: int, batch_total: int) -> str:
    """Construct the user prompt for the provided chunk group."""

    template = atomic_user_template()
    if not template:
        return ""

    if isinstance(group, dict):
        raw_chunks = group.get("chunks") or []
        if isinstance(raw_chunks, list):
            chunks_list = raw_chunks
        else:
            try:
                chunks_list = list(raw_chunks)
            except TypeError:
                chunks_list = []
    else:
        chunks_list = []

    doc_name = metadata.get("document") or "Document"
    discipline = metadata.get("pass_name") or metadata.get("discipline") or "General"
    user_query = metadata.get("user_query") or metadata.get("question") or metadata.get("query") or ""

    loop_pattern = re.compile(r"{{#for c in chunks}}(.*?){{/for}}", re.S)
    match = loop_pattern.search(template)
    chunk_template = match.group(1) if match else ""
    rendered_chunks: List[str] = []
    for chunk in chunks_list:
        if not isinstance(chunk, dict):
            continue
        text = s(chunk.get("text"))
        if not text:
            continue
        hier = chunk.get("hier") or {}
        clause = s(
            hier.get("clause")
            or chunk.get("section_number")
            or chunk.get("section_id")
            or ""
        )
        heading = s(
            hier.get("heading")
            or chunk.get("section_name")
            or chunk.get("section_title")
        )
        doc_id = s(chunk.get("doc_id") or chunk.get("document") or doc_name)
        page_span = chunk.get("page_span")
        if isinstance(page_span, (list, tuple)) and len(page_span) >= 2:
            page_repr = f"[{int(page_span[0])}, {int(page_span[1])}]"
        else:
            start = int(chunk.get("page_start") or chunk.get("page") or 1)
            end = int(chunk.get("page_end") or start)
            page_repr = f"[{start}, {end}]"
        prefix = s(chunk.get("prefix"))
        if not prefix:
            prefix_parts = [doc_id]
            if clause:
                prefix_parts.append(f"§{clause}")
            if heading:
                prefix_parts.append(f"— {heading}")
            prefix = " ".join(part for part in prefix_parts if part).strip()
            if prefix:
                prefix += ": "
        block = chunk_template
        block = block.replace("{{c.hier.clause}}", clause or "")
        block = block.replace("{{c.prefix}}", prefix or "")
        block = block.replace("{{c.text}}", text)
        block = block.replace("{{c.doc_id}}", doc_id)
        block = block.replace("{{c.page_span}}", page_repr)
        rendered_chunks.append(block.strip())

    if match:
        template = (
            template[: match.start()]
            + ("\n".join(rendered_chunks) if rendered_chunks else "(no excerpts)")
            + template[match.end():]
        )

    template = template.replace("{{std_name}}", doc_name)
    template = template.replace("{{discipline}}", discipline)
    template = template.replace("{{user_query}}", user_query)
    return template.strip()
