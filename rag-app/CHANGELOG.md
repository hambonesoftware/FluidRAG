# Changelog

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
