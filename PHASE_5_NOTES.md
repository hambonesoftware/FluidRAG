# Phase 5 Notes — Header Detection & Rechunk

## Summary
- Implemented header detection service with regex + typography heuristics, sequence repair, and section-aware rechunking.
- Added FastAPI route `/headers/join` returning header artifacts and mapped chunk data.
- Persisted `headers.json`, `section_map.json`, and `header_chunks.jsonl` under each document artifact root.

## Key Components
- `contracts/headers.py`: Pydantic models for headers, section assignments, and section-aligned chunks.
- `services/header_service`: controller orchestrating heuristics (`regex_bank`, `typo_features`), stitching, repair, and rechunk modules.
- `routes/headers.py`: async endpoint to drive header join + rechunk service.
- Tests in `backend/app/tests/unit/test_headers.py` cover end-to-end pipeline and sequence repair recovery.

## Heuristics Highlights
- Regex bank supports Appendix/Section numbering plus natural headings (Executive Summary, Introduction, etc.).
- Typography scorer boosts confidence using average size/weight when available.
- Stitcher merges contiguous fragments and deduplicates overlapping candidates.
- Sequence repair promotes low-score candidates to fill numbering gaps (e.g., missing A.2).

## Artifacts
- `headers.json`: list of detected headers with scores, ordinals, and contributing chunk IDs.
- `section_map.json`: chunk-to-header assignment records (subset when overlaps occur).
- `header_chunks.jsonl`: section-aligned aggregated chunks referencing underlying chunk IDs.
- Audit file `headers.audit.json` logs stage outcomes.

## Testing & Commands
- `ruff check backend`
- `black --check backend`
- `FLUIDRAG_OFFLINE=true pytest -q -o cache_dir=/tmp/pytest_cache -k "phase5"`
- `FLUIDRAG_OFFLINE=true pytest -q -o cache_dir=/tmp/pytest_cache`

All tests executed offline with `FLUIDRAG_OFFLINE=true`.

## Migrations
- None required.

## Follow-ups
- Consider richer typography integration once parse artifacts carry per-block font data.
- Future phases may extend `section_map.json` to include empty-section placeholders if desired.
