# Phase 4 — Chunk Service & Vector Indexes

## Goals
- UF chunking with sentence + typography boundaries; build sparse+dense indexes.

## Scope
- UF chunker (≈90 tokens, overlap 10–15); typography features.
- Sparse BM25; dense FAISS (local) and optional Qdrant (remote).
- Hybrid fusion function (alpha-weighted).

## Deliverables
- `uf_chunks.jsonl` + per-doc FAISS index; BM25 corpus persisted or in-memory.
- Retrieval API for internal use by passes.

## Acceptance Criteria
- Hybrid search returns relevant chunks on curated queries.
- Index build time within acceptable limits for medium PDFs.
