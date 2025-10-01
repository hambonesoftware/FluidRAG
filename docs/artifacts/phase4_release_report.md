# Phase 4 Release Readiness Report

## Config Snapshot
- Path: `docs/artifacts/phase4_config_snapshot.json`
- Upload: `max_mb=100`, allowed extensions `['.pdf']`, allowed MIME types `['application/pdf']`, temp dir `storage/uploads/tmp`, final dir `storage/uploads/final`, rate limit `60 req/min`.
- Parser: OCR enabled for languages `['eng']`; tuning enabled with EFHG weights (`regex=1.0`, `style=1.0`, `entropy=0.8`, `graph=1.1`, `fluid=0.9`, `llm_vote=1.0`); thresholds `header=0.65`, `subheader=0.5`; stitching `adjacency_weight=0.8`, `entropy_join_delta=0.15`, `style_cont_threshold=0.7`; sequence repair (`hole_penalty=0.4`, `max_gap_span_pages=2`, `min_schema_support=2`).
- Logging: level `INFO`, JSON output enabled.
- CORS: origins `['*']`, methods `['GET', 'POST']`, headers `['Authorization', 'Content-Type']`.

## End-to-End Validation
- Upload route: `POST /api/uploads` (multipart `file` field), HTTP 201.
- Document: `doc_01K6ESYD1QR21NK4AHWRMSJE4J` (`Epf-Co.pdf`, 47,991 bytes, SHA256 `3fc4bc96df188d6e7412e56eb8a4e3b1c4196eab5a30850952ec9a52f83b14e5`).
- Header results: 41 headers detected; Appendix sequence recovered with A1–A8 present (A5/A6 included).
- Result route: `GET /api/docs/{doc_id}/headers` returned nodes plus tuning profile; no hardcoded title promotions observed.

## Server Artifacts
- `/workspace/FluidRAG/rag-app/storage/parser/doc_01K6ESYD1QR21NK4AHWRMSJE4J/detected_headers.json`
- `/workspace/FluidRAG/rag-app/storage/parser/doc_01K6ESYD1QR21NK4AHWRMSJE4J/gaps.json`
- `/workspace/FluidRAG/rag-app/storage/parser/doc_01K6ESYD1QR21NK4AHWRMSJE4J/audit.html`
- `/workspace/FluidRAG/rag-app/storage/parser/doc_01K6ESYD1QR21NK4AHWRMSJE4J/audit.md`
- `/workspace/FluidRAG/rag-app/storage/parser/doc_01K6ESYD1QR21NK4AHWRMSJE4J/results.junit.xml`
- `/workspace/FluidRAG/rag-app/storage/parser/doc_01K6ESYD1QR21NK4AHWRMSJE4J/tuned.header_detector.toml`

## Edge-Case Validation
- Extension guard: uploading `fake.txt` returned 400 `unsupported_extension`.
- MIME guard: uploading text renamed `fake.pdf` returned 415 `unsupported_mime`.
- Size limit: uploading 105 MB `big.pdf` returned 413 `file_too_large`.
- Duplicate policy: re-upload of `Epf, Co.pdf` returned 200 with canonical doc ID and duplicate flag.
- Idempotency: immediate repeat of same upload returned 200 with identical doc ID and metadata.

## Test Suite
- `pytest -q` → 121 passed, 0 failed (warnings only for SwigPy types). No tuned config or junit overrides required beyond server artifacts.

## Deviations Fixed
- None – implementation matched finalstubs without additional code changes during validation.

## Recommendation
- **GO** – all acceptance checks, edge cases, and tests passed with required artifacts emitted.
