"""Adapters for vector and embedding integrations."""

from .db import upsert_document_record
from .llm import LLMClient, call_llm
from .storage import (
    StorageAdapter,
    assert_no_unmanaged_writes,
    ensure_parent_dirs,
    get_storage_guard,
    read_jsonl,
    reset_storage_guard,
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
    "StorageAdapter",
    "assert_no_unmanaged_writes",
    "write_json",
    "write_jsonl",
    "read_jsonl",
    "stream_read",
    "stream_write",
    "ensure_parent_dirs",
    "get_storage_guard",
    "reset_storage_guard",
    "upsert_document_record",
]
