# Phase 5 — Header Detection, Stitching & Rechunk

## Goals
- High-precision headers using regex + typography; repair sequences; section-aligned rechunking.

## Scope
- Heuristics (A.1, A-1, “Appendix A – ...”), typography thresholds, left-edge consistency.
- EFHG stitcher; aggressive sequence repair for holes.
- Emit `headers.json`, `section_map.json`, `header_chunks.jsonl`.

## Deliverables
- Deterministic mapping from UF chunk IDs to sections.
- Gaps filled when evidence supports it; false positives minimized.

## Acceptance Criteria
- Precision/recall on header benchmark ≥0.9.
- Section leakage on chunks ≤5%.
