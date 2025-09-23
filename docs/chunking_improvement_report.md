# FluidRAG Chunking Improvement Report

## Overview
- **Corpus:** 3 RFQ-style documents (Alpha, Bravo, Charlie)
- **Stages instrumented:** `raw_chunking`, `standard_chunks`, `fluid_chunks`, `hep_chunks`
- **Evaluation command:** `python -m chunking.evaluate --corpus data/corpus --config chunking/config.yaml`
- **Acceptance summary:**
  - `SectionPresence@Any` ↑ +25.0 pts (avg) vs. baseline
  - `NoBleed%` ↑ +50.0 pts (avg) vs. baseline
  - All configured pass views respect token budgets and hit available `must_sections`

## Baseline Observations
Instrumentation captured per-stage metrics (`out/eval/instrumentation/baseline`). Highlights:

| Doc | Stage | Chunk Count | % Cross Heading (fluid) | Avg Tokens | Section Coverage |
| --- | --- | ---: | ---: | ---: | --- |
| rfq_alpha | standard | 2 | 50.0 | 53 | 1,3 |
| rfq_bravo | standard | 2 | 50.0 | 49 | 4,5 |
| rfq_charlie | standard | 1 | 50.0 | 45 | 6 |

### Problem Cases
1. **Heading bleed:** `rfq_alpha` chunk glued sections `1)` and `2)` together, obscuring section 2 in lookups (`examples/rfq_alpha_before.json`).
2. **Footer noise:** `rfq_bravo` carried page numbers (`Page 12`) and roman numerals into chunks, polluting retrieval.
3. **Appendix glue:** `rfq_alpha` pricing table rows and follow-on bullets merged into a single chunk, breaking downstream table logic.

Each issue is visible in the baseline JSON examples under `examples/*_before.json`.

## Remediation Tactics
- **Hard heading breaks:** regex split on main/appx headings before fluid merges.
- **Artifact scrub:** removed lone digits, bullets, roman numerals at page boundaries.
- **List stitching:** joined wrapped bullet continuations (`- Provide` + `support structure`).
- **Appendix micro-chunking:** emitted ≤1200-char table-row chunks for pricing/schedule/compliance tables.
- **Soft splits for views:** view builder slices multi-heading chunks for allowlisted sections without mutating global cache.
- **HEP recalibration:** Shannon entropy × spec token density, doc-level z-normalized, stored as `meta.hep_entropy_z`.

## Results
Aggregated evaluation metrics (`out/eval/metrics.json`):

| Metric | Baseline Avg | Improved Avg | Δ |
| --- | ---: | ---: | ---: |
| SectionPresence@1 | 41.7 | 83.3 | +41.6 |
| SectionPresence@Any | 50.0 | 75.0 | +25.0 |
| NoBleed% | 50.0 | 100.0 | +50.0 |
| ArtifactLineRate | 0.0 | 0.0 | — |

### View Quality
All pass-specific views achieved 100% section precision and zero irrelevant tokens while staying within budgets.

| Pass | Tokens Used | Budget |
| --- | ---: | ---: |
| mechanical | 68 | 2200 |
| controls | 29 | 1700 |
| software | 9 | 1500 |
| pm | 55 | 2200 |

## Before / After Snapshots
| Doc | Baseline Snippet | Improved Snippet |
| --- | --- | --- |
| rfq_alpha | `1) Introduction … 2) Scope … Appendix B — Pricing Table …` | Separate chunks for `1)`, `2)`, `3)` plus two appendix row chunks. |
| rfq_bravo | `4) Mechanical … 5) Electrical … Appendix C … A1. Spare Parts…` | Heading-specific chunks, appendix schedule isolated, artifacts dropped. |
| rfq_charlie | `6) Controls … 7) Software … Appendix D Compliance Table …` | Distinct `6)` / `7)` paragraphs and two compliance micro-chunks. |

Full JSONs are published under `examples/*_after.json` for audit.

## Remaining Gaps & Follow-ups
- **Semantic heading classifier:** current regex misses stylistic headings (e.g., all-caps without numbering).
- **Learned artifact detector:** heuristics ignore mid-page headers that mimic roman numerals.
- **Adaptive HEP thresholds:** static z-thresholds may over-admit low-entropy tables in larger corpora; consider percentile-based gating.
- **View scoring:** placeholder BM25/overlap should be replaced with production retrieval stack when embeddings available.

## Conclusion
The shipped ruleset and evaluation harness materially improve chunk cleanliness, section coverage, and pass views while enforcing regression gates via golden hashes and pytest.
