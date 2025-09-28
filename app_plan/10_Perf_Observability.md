# Phase 10 — Performance, Observability & Hardening

## Goals
- Profile hot paths; add logging, tracing, metrics; tune timeouts and batch sizes.

## Scope
- JSON logging helper; correlation IDs; stage audit records.
- Profiling guides and perf targets (P50/P95).
- Backpressure/backoff tuning for LLM and vector calls.

## Deliverables
- Configurable timeouts & batch sizes in `config.py` / env.
- Documentation for profiling and tuning.

## Acceptance Criteria
- Pipeline latency meets targets on dev machine.
- Logs provide actionable visibility into failures.
