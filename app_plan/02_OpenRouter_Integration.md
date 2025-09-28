# Phase 2 — OpenRouter Client Integration

## Goals
- Implement and validate OpenRouter client per spec (sync, async stream, embeddings).

## Scope
- Files under `backend/app/llm/`:
  - `utils.py`, `utils/envsafe.py` (headers, masking, logging meta)
  - `openrouter.py` (thin sync wrapper)
  - `clients/openrouter.py` (sync + SSE streaming + embeddings + retries with jitter)

## Deliverables
- Env-driven headers: Authorization, HTTP-Referer, X-Title.
- SSE parsing with `httpx.AsyncClient.aiter_lines()` and idle timeout handling.
- Retries on 429/5xx; masked header logging (CID).

## Acceptance Criteria
- Local smoke test hits `/chat/completions` and streams tokens.
- Embeddings endpoint returns vectors for sample inputs.
