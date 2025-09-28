"""Adapters for vector and embedding integrations."""

from .db import upsert_document_record
from .llm import LLMClient, call_llm
from .storage import (
    ensure_parent_dirs,
    read_jsonl,
    stream_read,
    stream_write,
    write_json,
    write_jsonl,
)
from .vectors import (
    BM25Index,
    EmbeddingModel,
    FaissIndex,
    QdrantIndex,
    hybrid_search,
)

__all__ = [
    "EmbeddingModel",
    "BM25Index",
    "FaissIndex",
    "QdrantIndex",
    "hybrid_search",
    "LLMClient",
    "call_llm",
    "write_json",
    "write_jsonl",
    "read_jsonl",
    "stream_read",
    "stream_write",
    "ensure_parent_dirs",
    "upsert_document_record",
]
