# Changelog

## [Phase 8] - 2025-09-30
### Added
- Frontend MVVM dashboard with upload controls, pipeline status polling, and pass result rendering.
- Artifact download UX wired to `/pipeline/artifacts` with offline awareness and DOM event signaling.
- Node-backed pytest suite exercising the PipelineVM polling loop and ResultsView artifact handling.

### Changed
- Refreshed static frontend markup and styling to support live progress indicators, pass metadata, and offline banners.
- API client extended with artifact URL helper and richer JSON fallback handling.

### Documentation
- README instructions for the new dashboard workflow and offline behavior.

### Verification
- **Features:** Completed Phase 8 audit confirming MVVM models, view-models, and views match the
  plan; traceability captured in `reports/phase_8_verification.md`.
- **Fixes:** Added pytest markers for phases 7–8, switched FastAPI startup/shutdown hooks to the
  lifespan API to eliminate deprecation warnings, and made normalization manifests emit
  timezone-aware timestamps.
- **Migrations:** Not applicable.
- **Compatibility:** Backend test suite now runs with `-W error`; Node.js remains required for the
  frontend harness.

## [Phase 7] - 2025-09-29
### Added
- Pipeline orchestrator FastAPI routes for `/pipeline/run`, `/pipeline/status/{doc_id}`, `/pipeline/results/{doc_id}`, and `/pipeline/artifacts` with audit emission and artifact streaming security.
- Validation of pass manifests/results using the domain contracts to guarantee consistent response shapes.
- Unit test coverage for orchestrator flows including success, validation, error, and streaming scenarios.

### Changed
- Hardened artifact streaming to restrict access to the configured `ARTIFACT_ROOT` and surface decoded audit information through the status endpoint.

### Documentation
- README instructions for triggering the orchestrator endpoints and retrieving streamed artifacts.

### Verification
- Confirmed orchestrator endpoints, artifact streaming guards, and associated tests align with Phase 7 plans during audit (see reports/phase_7_verification.md).
