# Phase 3 — Upload & Parser Service (Fan-Out/Fan-In)

## Goals
- Normalize files then run async multi-pass parsing to produce enriched artifact.

## Scope
- `upload_service` validate + normalize (pdfplumber / PyMuPDF hooks).
- `parser_service` subtasks: language detection, text blocks, tables, images, links, OCR router, reading order, semantics, lists/bullets; merge into `parse.enriched.json`.

## Deliverables
- Async fan-out via `asyncio.create_task` with timeouts; fan-in merge.
- Pluggable OCR with page confidence thresholds.
- Deterministic IDs for blocks; bbox, fonts, styles.

## Acceptance Criteria
- Enriched parse produced on real sample PDFs.
- Page coverage ≥95%; reading order audited on samples.
