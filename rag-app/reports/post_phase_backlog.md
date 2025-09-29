# Post-Phase Backlog — Release Handover

## High Priority
- **Deployment automation** — produce container images and CI/CD workflows for hosting
the FastAPI backend and static frontend. Include secrets management for OpenRouter
credentials and environment promotion guards.
- **User onboarding tour** — extend the MVVM dashboard with a guided tour explaining
artifact downloads, pass results, and troubleshooting entry points.

## Medium Priority
- **Retrieval analytics** — surface per-pass retrieval metrics (NDCG, MRR) in the
frontend and audit payloads to support ongoing tuning.
- **Artifact retention policy** — background job to expire artifacts and audits
beyond the configured retention window with opt-in archiving.
- **LLM provider abstraction** — adapt OpenRouter client to a provider interface so
additional vendors can be plugged in without touching the pipeline services.

## Low Priority
- **Dark mode polish** — apply design system updates to the dashboard while keeping
accessibility contrast targets.
- **Internationalisation hooks** — prepare frontend copy for localisation by moving
strings into a central catalogue and wiring language selection to pipeline headers.
- **Benchmark automation** — schedule the `bench_phase3.py` harness to run nightly
and trend latency data across commits for regression detection.
