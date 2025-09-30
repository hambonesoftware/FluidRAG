# Upload & Parser Phase 1 Gap Report

## Context
- **Repository overview:** Current stack runs a FastAPI backend (`run.py`) with configurable settings via `backend.app.config.Settings`, serving REST routes for upload, parser, chunking, headers, passes, and orchestration.【F:rag-app/run.py†L23-L120】【F:rag-app/backend/app/main.py†L62-L100】【F:rag-app/backend/app/config.py†L14-L208】
- **Phase 1 goal:** Per `parser_upgrade_plan/overview.md` and `phase1_repo_discovery.md`, Phase 1 inventories uploader/parser behaviour and highlights gaps to reach the production-grade plan.【F:parser_upgrade_plan/overview.md†L1-L9】【F:parser_upgrade_plan/phase1_repo_discovery.md†L1-L10】
- **Future intent:** Finalstubs expect robust upload normalization, OCR, parser fan-out, and artifact manifesting across the backend (`normalize_pdf`, `try_ocr_if_needed`, `parse_and_enrich`, `merge_all`, etc.).【F:finalstubs_latest.json†L520-L626】【F:finalstubs_latest.json†L635-L746】【F:finalstubs_latest.json†L795-L930】

## What exists (good enough)
- FastAPI app factory with correlation-ID middleware, permissive CORS, and `/health` probe; CLI runner spins backend/frontend with shared JSON logging.【F:rag-app/backend/app/main.py†L25-L100】【F:rag-app/run.py†L23-L120】【F:rag-app/backend/app/util/logging.py†L20-L185】
- Upload route `/upload/normalize` invokes `ensure_normalized` which validates IDs, writes `normalize.json`, and emits a SHA-256 manifest plus doc manifest registration.【F:rag-app/backend/app/routes/upload.py†L22-L34】【F:rag-app/backend/app/services/upload_service/upload_controller.py†L35-L105】【F:rag-app/backend/app/services/upload_service/packages/emit/manifest.py†L12-L30】【F:rag-app/backend/app/adapters/db.py†L13-L32】
- Parser route `/parser/enrich` triggers a fan-out/fan-in pipeline that runs heuristic extractors (text, tables, images, links, language, OCR shim), generates a merged `parse.enriched.json`, and logs span metadata.【F:rag-app/backend/app/routes/parser.py†L17-L33】【F:rag-app/backend/app/services/parser_service/parser_controller.py†L42-L200】【F:rag-app/backend/app/services/parser_service/packages/extract/pdf_text.py†L8-L23】【F:rag-app/backend/app/services/parser_service/packages/merge/merger.py†L8-L42】
- Pipeline orchestrator surfaces `/pipeline/status`, `/pipeline/results`, and `/pipeline/artifacts` with path whitelisting for artifact streaming; tests cover upload, parser, orchestrator routes, and full pipeline e2e.【F:rag-app/backend/app/routes/orchestrator.py†L201-L345】【F:rag-app/backend/app/tests/unit/test_upload.py†L1-L55】【F:rag-app/backend/app/tests/unit/test_parser.py†L1-L47】【F:rag-app/backend/app/tests/e2e/test_pipeline_e2e.py†L1-L55】

## Gaps / Risks
- **High – Real file ingestion missing**  
  *Impact:* Cannot accept actual binary uploads; relies on JSON text or filesystem path, so production upload UX (multipart, size enforcement, streaming) is absent.  
  *Evidence:* Upload route only accepts `UploadRequest` JSON and runs in threadpool without file bytes or content-type guards.【F:rag-app/backend/app/routes/upload.py†L15-L34】  
  *Finalstubs:* `upload_service` plan assumes genuine normalization of uploaded files, not text echoes.【F:finalstubs_latest.json†L520-L546】
- **High – Normalization is stubbed**  
  *Impact:* `normalize_pdf` fabricates structure from plaintext, missing pdfplumber/PyMuPDF extraction, bbox fidelity, and style metadata; downstream parser cannot meet quality targets.  
  *Evidence:* Function splits text on blank lines, infers fonts heuristically, and never touches PDF bytes.【F:rag-app/backend/app/services/upload_service/packages/normalize/pdf_reader.py†L17-L153】  
  *Finalstubs:* Expected to “extract text/layout/style into a normalized JSON.”【F:finalstubs_latest.json†L520-L546】
- **High – OCR fallback is synthetic**  
  *Impact:* `try_ocr_if_needed` clones existing blocks and injects placeholder text; no Tesseract or confidence-driven merge, so scanned docs remain unreadable.  
  *Evidence:* Adds static “OCR recovered text” strings when coverage < threshold.【F:rag-app/backend/app/services/upload_service/packages/normalize/ocr.py†L15-L83】  
  *Finalstubs:* Requires real OCR merge layer.【F:finalstubs_latest.json†L553-L577】
- **High – Parser extractors lack true enrichment**  
  *Impact:* Parser pipeline reuses normalized JSON with trivial heuristics; no PyMuPDF/pdfplumber integration, table/figure detection, or OCR tokens, undermining EFHG and retrieval quality.  
  *Evidence:* `extract_text_blocks`, `extract_tables`, `extract_images`, `extract_links`, `detect_language`, and `merge_all` operate on normalized dicts with regex heuristics only.【F:rag-app/backend/app/services/parser_service/packages/extract/pdf_text.py†L8-L23】【F:rag-app/backend/app/services/parser_service/packages/extract/tables.py†L11-L31】【F:rag-app/backend/app/services/parser_service/packages/extract/images.py†L8-L20】【F:rag-app/backend/app/services/parser_service/packages/extract/links.py†L11-L25】【F:rag-app/backend/app/services/parser_service/packages/detect/language.py†L16-L34】【F:rag-app/backend/app/services/parser_service/packages/merge/merger.py†L8-L42】  
  *Finalstubs:* Planned `parse_and_enrich` fan-out should return enriched artifacts suitable for downstream EFHG and chunking.【F:finalstubs_latest.json†L635-L746】
- **High – EFHG & sequence repair absent**  
  *Impact:* Finalstubs list regex/style/entropy/graph/LLM voting components and tuned headers pipeline; current codebase lacks these modules entirely, preventing parity with RAG-Anything header detection.  
  *Evidence:* No implementations for EFHG packages under `header_service` match finalstubs (planned functions missing).【F:finalstubs_latest.json†L1400-L1495】  
  *Finalstubs:* Expect `join_and_rechunk` pipeline with heuristics, stitching, and repair layers.【F:finalstubs_latest.json†L1400-L1469】
- **Medium – Validation/security gaps**  
  *Impact:* No MIME sniffing, extension allowlist, size checks, antivirus/quarantine, rate limiting, or auth; open CORS leaves upload endpoint exposed.  
  *Evidence:* Validator checks only whitespace/path traversal; create_app allows all origins/methods/headers.【F:rag-app/backend/app/services/upload_service/packages/guards/validators.py†L10-L38】【F:rag-app/backend/app/main.py†L79-L86】  
  *Finalstubs:* Upload plan implies hardened validators and quarantine hooks before normalization.【F:finalstubs_latest.json†L480-L518】
- **Medium – Doc ID prevents dedupe**  
  *Impact:* `make_doc_id` seeds SHA-1 with timestamp, guaranteeing uniqueness but blocking checksum-based deduplication & idempotency.  
  *Evidence:* Timestamp prefix + truncated digest ensures every call produces a new doc_id even for same file.【F:rag-app/backend/app/services/upload_service/upload_controller.py†L86-L91】  
  *Finalstubs:* Manifest/checksum flow should enable duplicate detection before heavy processing.【F:finalstubs_latest.json†L595-L624】
- **Low – Async orchestration uses blocking pattern**
  *Impact:* `parse_and_enrich` wraps async fan-out via `asyncio.run` inside threadpool, limiting reuse in async contexts and complicating cancellation.
  *Evidence:* Controller executes `_fan_out` via `asyncio.run` in synchronous function.【F:rag-app/backend/app/services/parser_service/parser_controller.py†L124-L148】
  *Finalstubs:* Plan implies native async fan-out ready for awaited pipelines.【F:finalstubs_latest.json†L635-L690】

### Resolved gaps summary

- **Multipart ingestion & validation** – `/upload/normalize/file` streams `UploadFile` payloads into a quarantine directory, enforcing extension/MIME allowlists, double-extension guards, size limits, and SHA-256 deduplication before normalization.【F:rag-app/backend/app/routes/upload.py†L12-L83】【F:rag-app/backend/app/services/upload_service/packages/storage/filesystem.py†L1-L125】【F:rag-app/backend/app/services/upload_service/packages/guards/validators.py†L1-L114】
- **Checksum-stable doc IDs** – `make_doc_id` now derives identifiers from file checksums and sanitized filenames, providing idempotent lookups while maintaining backward compatibility for legacy callers.【F:rag-app/backend/app/services/upload_service/upload_controller.py†L103-L132】
- **PDF normalization fidelity** – `normalize_pdf` consumes real PDF bytes via PyMuPDF/pdfplumber to emit block geometry, styles, coverage metrics, and image metadata; plaintext fixtures fall back to deterministic parsing for tests.【F:rag-app/backend/app/services/upload_service/packages/normalize/pdf_reader.py†L1-L230】
- **OCR with graceful degradation** – `try_ocr_if_needed` attempts Tesseract-powered extraction and injects structured placeholders when OCR tooling is unavailable, ensuring coverage metrics and audit trails remain accurate.【F:rag-app/backend/app/services/upload_service/packages/normalize/ocr.py†L1-L168】
- **Parser enrichment overhaul** – Parser fan-out sequentially times text, table, image, link, OCR, semantics, and list extraction using PyMuPDF/pdfplumber/langdetect utilities, eliminating the blocking `asyncio.run` pattern and producing richer artifacts.【F:rag-app/backend/app/services/parser_service/parser_controller.py†L1-L149】【F:rag-app/backend/app/services/parser_service/packages/extract/tables.py†L1-L52】【F:rag-app/backend/app/services/parser_service/packages/extract/images.py†L1-L61】【F:rag-app/backend/app/services/parser_service/packages/extract/links.py†L1-L45】【F:rag-app/backend/app/services/parser_service/packages/detect/language.py†L1-L40】

### Phase 1 follow-up status

- High-severity uploader/parser gaps from Phase 1 are closed; remaining work centers on EFHG/sequence repair delivery for headers.
- Observability now benefits from checksum-stable doc IDs and expanded manifest metadata; future iterations can extend metrics/exporters.

## Recommendations for Phase 2
- Replace upload route with multipart/form-data handler, stream writes to quarantine, enforce size/type/MIME, and wire checksum dedupe before normalization (addresses **Real file ingestion** & **Validation/security gaps**). Align doc_id with checksum-based stable IDs.
- Implement genuine PDF normalization using PyMuPDF/pdfminer plus layout/style capture; persist full block geometry and fonts to satisfy downstream parser expectations (**Normalization stubbed**).
- Integrate OCR (e.g., pytesseract) triggered by coverage metrics, merge text with confidence tracking, and persist page-level audit (**OCR synthetic**).
- Rebuild parser fan-out to consume normalized artifact bytes, add structured extractors (tables/images/links via pdfplumber, language detection via langdetect/spacy), and emit enriched schema powering EFHG (**Parser extractors lacking**).
- Deliver EFHG modules per finalstubs (regex/style/entropy/graph scoring, Fluid alignment, LLM voting, sequence repair, tuned header configs) and ensure headers route exports tuned TOML/artifacts (**EFHG absent**).
- Harden Observability with request metrics and doc_id propagation into artifacts; add antivirus hooks or scanning pipeline prior to normalization (**Validation/security gaps**).
- Refactor parser controller into async callable returning coroutine to avoid nested `asyncio.run` and improve orchestration composability (**Async orchestration**).

## RAG-Anything parity & beyond
- **Parity achieved:** Structured JSON logging with correlation IDs and span timings, pipeline audit manifests, and artifact streaming guards mirror RAG-Anything observability basics.【F:rag-app/backend/app/util/logging.py†L20-L185】【F:rag-app/backend/app/routes/orchestrator.py†L201-L345】
- **Below parity:** Upload lacks binary ingestion safeguards, checksum dedupe, MIME sniffing, and quarantine; parser lacks true PDF extraction, OCR, semantic enrichment, and EFHG pipeline—all core to RAG-Anything’s robustness.【F:rag-app/backend/app/routes/upload.py†L22-L34】【F:rag-app/backend/app/services/upload_service/packages/normalize/pdf_reader.py†L68-L153】【F:rag-app/backend/app/services/parser_service/parser_controller.py†L42-L200】
- **Beyond target opportunities:** Phase 2 can exceed parity by adding antivirus scanning, rate limiting, configurable storage tiers, metrics exporters, and CI-ready header tuning workflow aligned with the finalstubs vision of checksum dedupe, MIME sniffing, EFHG tuning, and artifact manifests.【F:finalstubs_latest.json†L480-L626】【F:finalstubs_latest.json†L1400-L1469】
