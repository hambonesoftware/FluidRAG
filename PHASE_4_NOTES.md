# Phase 4 Notes — Chunk Service & Vector Indexes

## Overview
- Added chunk service package with sentence segmentation, typography features, UF chunk heuristics, and offline-friendly sparse+dense index builders.
- Introduced `/chunk/uf` FastAPI route returning persisted `uf_chunks.jsonl` artifacts and optional index manifest.
- Implemented vector adapter abstractions (BM25, Faiss-style cosine store, Qdrant stub) plus hybrid retrieval helper for future passes.
- Extended settings/ENV to control `CHUNK_TARGET_TOKENS` and `CHUNK_TOKEN_OVERLAP`, updated docs and configuration samples accordingly.

## Running the Chunk Pipeline
1. Normalize and parse content as in earlier phases.
2. Invoke the chunk endpoint:
   ```bash
   curl -s -X POST http://127.0.0.1:8000/chunk/uf \
     -H 'Content-Type: application/json' \
     -d '{"doc_id": "<doc_id>", "normalize_artifact": "<parse_enriched_path>"}'
   ```
3. Inspect `${ARTIFACT_ROOT}/<doc_id>/uf_chunks.jsonl`, `index.manifest.json`, and `chunk.audit.json` for persisted artifacts.

## Configuration
- `CHUNK_TARGET_TOKENS` (default 90) — approximate token budget per UF chunk.
- `CHUNK_TOKEN_OVERLAP` (default 12) — token overlap between adjacent chunks.

## Tests & Quality Gates
- Unit tests cover chunk controller + retrieval utilities: `pytest -q rag-app/backend/app/tests/unit/test_chunk.py`
- Full offline suite: `FLUIDRAG_OFFLINE=true pytest -q -o cache_dir=/tmp/pytest_cache`
- Lint & format: `ruff check rag-app`, `black --check rag-app`

## Notes
- Dense index builder uses deterministic hashing to remain offline-friendly while providing cosine similarity search.
- Qdrant adapter stores vectors in-memory and logs when running offline; ready for future remote integration once allowed.
