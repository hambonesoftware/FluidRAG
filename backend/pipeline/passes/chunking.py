"""Chunk preparation helpers for the pass pipeline."""
from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional

from backend.persistence import get_preprocess_cache
from backend.state import get_state
from backend.utils.strings import s

from ..fluid import fluid_refine_chunks  # type: ignore[import]
from ..hep_cluster import hep_cluster_chunks  # type: ignore[import]
from .constants import CHUNK_GROUP_TOKEN_LIMIT

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
            sidecar_dir = os.path.join("sidecars", session_id)
            chunks = [
                dict(chunk)
                for chunk in section_bounded_chunks_from_pdf(
                    pdf_path,
                    sidecar_dir=sidecar_dir,
                    session_id=session_id,
                )
            ]

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

    refined = fluid_refine_chunks(chunks)
    enriched = hep_cluster_chunks(refined)
    state.refined_chunks = refined
    state.clustered_chunks = enriched
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
