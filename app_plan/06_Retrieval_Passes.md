# Phase 6 — Retrieval + Five Structured RAG Passes

## Goals
- Domain-specific passes (mechanical, electrical, software, controls, PM) with schema-bound JSON and citations.

## Scope
- Hybrid retrieval + physics-inspired re-rankers (flow, energy, graph).
- Context compositor with dedupe and token budget.
- Prompts per domain; validate JSON against schemas.

## Deliverables
- `data/{doc}/passes/{name}.json` with answer + retrieval trace.
- Citation fields = header path + chunk IDs.

## Acceptance Criteria
- JSON schema validation = 100% green.
- Manual spot checks confirm correctness on sample docs.
