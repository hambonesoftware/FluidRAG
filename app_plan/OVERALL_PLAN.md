# RAG App Development Plan — Overall (2025-09-28)

This plan covers the end-to-end build of the RAG application with MVVM frontend, FastAPI backend, siloed services, and OpenRouter integration. It is organized by phases, each with scope, outcomes, acceptance criteria, risks, and deliverables.

## Guiding Principles
- Separation of concerns: orchestrator ⇢ service entries ⇢ controllers ⇢ packages (pure logic) ⇢ adapters.
- Files ≤ 500 lines. Split by concern when needed.
- Deterministic contracts (Pydantic v2) between layers.
- Robustness: retries, circuit breaker, streaming I/O, vector indexes, tests wired to real data.
- Environment: venv, `python run.py`, no Docker required.
- LLM provider: **OpenRouter** (exact headers/endpoint as defined in `backend/app/llm/...`).

## Phases
1. **Project Foundations & Tooling**
2. **OpenRouter Client Integration**
3. **Upload & Parser Service (fan-out/fan-in)**
4. **Chunk Service & Vector Indexes**
5. **Header Detection, Stitching & Rechunk**
6. **Retrieval + Five Structured RAG Passes**
7. **API Routes & Orchestrator**
8. **Frontend MVVM (basic) & Streaming Results**
9. **Testing Strategy & Real Data Fixtures**
10. **Performance, Observability & Hardening**
11. **Release Readiness & Handover**

## Milestones
- M1: Foundations + OpenRouter client usable end-to-end.
- M2: Parser produces enriched artifact on real PDFs.
- M3: Chunking + vector search with hybrid fusion.
- M4: Headers & section-aligned rechunk operational.
- M5: Five RAG passes return schema-valid JSON with citations.
- M6: Orchestrated pipeline via `/pipeline/run`, with streaming artifact download.
- M7: Tests (unit + E2E) consistently green; profiling targets met.

## Success Metrics
- Parser accuracy: ≥95% page coverage with correct reading order on test set.
- Chunker cohesion: ≤5% cross-section leakage in UF chunks (audited).
- Retrieval NDCG@10: ≥0.75 on curated queries.
- Pass JSON validity: 100% schema-valid; citation hit-rate ≥0.9.
- P50/P95 latency for pipeline (1 medium PDF): ≤45s / ≤90s on dev machine.
- Error budget: <1% transient failures after retries.

## Risks & Mitigations
- **OCR quality variance** → pluggable OCR router + page-level confidence gating.
- **Table extraction fragility** → dual strategy (vector PDF vs scanned) + regression tests.
- **Token budget pressure** → context composer with dedupe & budget guardrails.
- **LLM rate limits** → backoff + circuit breaker + batch sizing.
