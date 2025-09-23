"""Chunk preparation helpers for the pass pipeline."""
from __future__ import annotations

import json
import logging
import os

from datetime import UTC, datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


from backend.persistence import get_preprocess_cache
from backend.prompts import PASS_PROMPTS
from backend.state import get_state
from backend.utils.strings import s

from ..fluid import fluid_refine_chunks  # type: ignore[import]
from ..hep_cluster import hep_cluster_chunks  # type: ignore[import]
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
    from ..preprocess import (  # type: ignore[import]
        approximate_tokens,
        section_bounded_chunks_from_pdf,
    )
except Exception:  # pragma: no cover - compatibility shim

    def approximate_tokens(text: str) -> int:
        """Fallback token approximation if preprocess helpers are unavailable."""

        if not text:
            return 0
        return max(1, len(text) // 4)

    def section_bounded_chunks_from_pdf(
        pdf_path: str,
        sidecar_dir: Optional[str] = None,
        tok_budget_chars: int = 6400,
        overlap_lines: int = 3,
        session_id: Optional[str] = None,
    ) -> Iterable[Dict[str, Any]]:
        raise RuntimeError("section_bounded_chunks_from_pdf unavailable")


def ensure_chunks(session_id: str) -> List[Dict[str, Any]]:
    """Load or derive chunks for the provided session."""

    state = get_state(session_id)
    if state is None:
        raise ValueError("Unknown session; upload and preprocess the document first.")

    sidecar_dir = os.path.join("sidecars", session_id)
    try:
        os.makedirs(sidecar_dir, exist_ok=True)
    except Exception:  # pragma: no cover - defensive
        log.exception("[chunking] failed to ensure sidecar directory %s", sidecar_dir)

    if state.pre_chunks is not None and state.pre_chunks:
        chunks = [dict(chunk) for chunk in state.pre_chunks]
    else:
        cached_pre = get_preprocess_cache(getattr(state, "file_hash", None))
        if cached_pre and cached_pre.get("chunks"):
            cached_chunks = [dict(chunk) for chunk in cached_pre.get("chunks", [])]
            state.pre_chunks = cached_chunks
            chunks = cached_chunks
        else:
            pdf_path = state.file_path
            if not pdf_path or not os.path.exists(pdf_path):
                uploads_dir = os.getenv("UPLOAD_FOLDER", "uploads")
                pdf_path = os.path.join(uploads_dir, f"{session_id}.pdf")
            chunks = [
                dict(chunk)
                for chunk in section_bounded_chunks_from_pdf(
                    pdf_path,
                    sidecar_dir=sidecar_dir,
                    session_id=session_id,
                )
            ]

    raw_snapshot = [dict(chunk) for chunk in chunks]

    document_name = state.filename or "Document"
    for chunk in chunks:
        chunk.setdefault("document", document_name)
        chunk.setdefault("section_number", chunk.get("section_id") or "")
        chunk.setdefault("section_name", chunk.get("section_title") or "")
        chunk.setdefault("page_start", chunk.get("page_start") or chunk.get("page") or 1)
        chunk.setdefault(
            "page_end",
            chunk.get("page_end") or chunk.get("page") or chunk.get("page_start") or 1,
        )
        chunk.setdefault("text", chunk.get("text", ""))
        chunk.setdefault("meta", {})


    standard_snapshot = [dict(chunk) for chunk in chunks]

    refined = fluid_refine_chunks(chunks)
    fluid_snapshot = [dict(chunk) for chunk in refined]

    enriched = hep_cluster_chunks(refined)
    hep_snapshot = [dict(chunk) for chunk in enriched]

    state.refined_chunks = refined
    state.clustered_chunks = enriched
    state.chunk_stage_snapshots = {
        "raw_chunking": raw_snapshot,
        "standard_chunks": standard_snapshot,
        "fluid_chunks": fluid_snapshot,
        "hep_chunks": hep_snapshot,
    }
    return enriched


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


def format_chunk_for_prompt(chunk: Dict[str, Any], idx: int, total: int) -> str:
    """Return a formatted prompt segment for the supplied chunk."""

    doc = s(chunk.get("document")) or "Document"
    sec_num = s(chunk.get("section_number") or chunk.get("section_id"))
    sec_name = s(chunk.get("section_name") or chunk.get("section_title"))
    page_start = chunk.get("page_start") or chunk.get("page") or 1
    page_end = chunk.get("page_end") or page_start
    body = s(chunk.get("text"))
    header_bits = [f"Document: {doc}"]
    if sec_num or sec_name:
        section_label = " ".join(bit for bit in [sec_num, sec_name] if bit).strip()
        header_bits.append(f"Section: {section_label}")
    header_bits.append(f"Pages: {page_start}-{page_end}")
    header = " \u2022 ".join(header_bits)
    return f"<<<CHUNK {idx + 1} OF {total}>>>\n{header}\n{body}\n<<<END CHUNK {idx + 1}>>>"


def build_user_prompt(metadata: Dict[str, Any], group: Dict[str, Any], batch_index: int, batch_total: int) -> str:
    """Construct the user prompt for the provided chunk group."""

    if isinstance(group, dict):
        raw_chunks = group.get("chunks") or []
        if isinstance(raw_chunks, list):
            chunks_list = raw_chunks
        else:
            try:
                chunks_list = list(raw_chunks)
            except TypeError:
                chunks_list = []
        token_estimate = group.get("token_estimate", 0)
    else:
        chunks_list = []
        token_estimate = 0

    chunk_texts = [
        format_chunk_for_prompt(chunk, idx, len(chunks_list))
        for idx, chunk in enumerate(chunks_list)
        if isinstance(chunk, dict) and s(chunk.get("text"))
    ]
    document = metadata.get("document") or "Document"
    lines = [
        f"DOCUMENT_METADATA:\n- Document: {document}\n- Session: {metadata.get('session_id', '')}",
        f"BATCH_INFO: batch {batch_index + 1} of {batch_total}; approx {token_estimate} tokens",
        "DOCUMENT_TEXT:",
        "\n\n".join(chunk_texts) if chunk_texts else "(no text)",
        "Return results exactly as instructed in the system prompt. Do not omit CSV or JSON sections.",
    ]
    return "\n\n".join(lines).strip()
