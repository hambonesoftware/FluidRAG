"""Header detection service facade."""

from __future__ import annotations

from pydantic import BaseModel

from .header_controller import HeaderJoinInternal
from .header_controller import join_and_rechunk as controller_join_and_rechunk


class HeaderJoinResult(BaseModel):
    """Header and rechunking outputs."""

    doc_id: str
    headers_path: str
    section_map_path: str
    header_chunks_path: str
    header_count: int
    recovered_count: int


def join_and_rechunk(doc_id: str, chunks_artifact: str) -> HeaderJoinResult:
    """Heuristics+LLM headers, sequence repair, section rechunk."""
    internal: HeaderJoinInternal = controller_join_and_rechunk(
        doc_id=doc_id, chunks_artifact=chunks_artifact
    )
    return HeaderJoinResult(**internal.model_dump())


__all__ = ["HeaderJoinResult", "join_and_rechunk"]
