# Appendix Header Recovery Playbook

This note collects production-ready techniques for surfacing missing appendix
headers—specifically **A5** and **A6** in RFQ-style documents—when PDF
segmentation or typography is unreliable. Each technique maps to an existing
stage in the FluidRAG pipeline so you can bolt it onto the current flow without
a wholesale rewrite.

## Pre-ingest (make the text exist the way you need)

1. **Redundant line segmentation ensemble (vote & merge).**
   - Run two or three independent segmenters (PDF text layout, OCR, and a
     punctuation-aware splitter work well).
   - Union their header detections using normalized text, then keep a line when
     _any_ segmenter emits `^A[56]\.` within ±3 lines of A4/A7, even if the
     primary pass missed it.

2. **Unicode + glyph normalization at the byte level.**
   - Normalize byte-level variants of spaces and dots _before_ regex checks.
   - Strip zero-width characters and map confusable glyphs (Latin `A` vs.
     Cyrillic `А`, etc.) so visually correct headers survive.

3. **Header-first hard splits.**
   - Treat patterns such as `^\d+\)` and `^A\d+\.` as hard record boundaries
     so a wrapped appendix title always starts a fresh record instead of being
     swallowed by the previous paragraph.

## Header detection (turn "likely" into "certain")

4. **Sequence model for header tagging.**
   - Train a lightweight tagger (HMM, CRF, or tiny BiLSTM) on header vs. body
     using features you already capture (font size, bold, caps ratio, regex
     hits, indent).
   - Decode with Viterbi and enforce monotonic transitions `A3→A4→A5→A6→A7`; if
     the sequence has a gap, the model boosts nearby borderline lines to fill
     A5/A6.

5. **Expected-neighbor rescoring (gap fill).**
   - Build a finite-state graph over appendix states and penalize missing
     transitions during inference.
   - Reward candidate headers that appear within ±_N_ lines of the expected
     position so borderline lines near the gap get promoted into A5/A6.

6. **Span-joiner with soft unwrap.**
   - If a header token (e.g., `A5.`) is followed by a short line (<6 tokens),
     join it with the next line and rescore as one span.
   - This repairs PDFs that break the appendix number and the title across
     separate lines.

## Indexing (so retrieval can actually fetch them)

7. **Header shards & multi-granularity indexing.**
   - Emit dedicated appendix header shards (≈60–120 tokens) alongside the
     standard micro- and macro-chunks and store fields such as
     `{header_text, header_id, page, char_span}`.
   - Fuse retrieval results using Reciprocal Rank Fusion (RRF/RRFi with `k=60`)
     so a header-only hit can rescue a miss from the longer chunks.

8. **ColBERT late-interaction heads for headers.**
   - Train or fine-tune a ColBERT-style encoder on short appendix header
     strings and run late-interaction scoring against all lines on appendix
     pages to stay robust to spacing/character noise.

## Retrieval (at question time)

9. **Sequence-aware re-query.**
   - When retrieval yields adjacent appendix headers but skips A5 or A6,
     auto-issue a follow-up query constrained to the same page ±1 and regex
     patterns `^A[56]\.` (plus variants like `A 5`).

10. **GraphRAG over a document outline.**
    - Construct a lightweight outline graph with edges between sequential
      appendix nodes and always include direct neighbors in the retrieved set,
      even when their textual score is slightly below threshold.

## Post-selection (after candidate scoring)

11. **Monotone dynamic-programming repair.**
    - Apply a DP pass that maximizes the score of a contiguous appendix
      sequence while penalizing skipped states so borderline candidates for A5
      or A6 get promoted whenever they avoid a gap.

12. **Self-consistency multi-decode (LLM assist).**
    - Run a small ensemble of LLM decodes over the appendix region only.
    - Intersect or majority-vote the outputs; if A5/A6 appear consistently but
      are missing from the final header set, trigger a focused rescan (see #6
      and #9) and elevate the best candidate.

## Production drop-ins

- **Neighbor rescue micro-pass.**
  - If `{A3, A4, A7, A8}` are present but `{A5, A6}` are not, rescan ±10 lines
    around the gap, normalize at the byte level, soft-unwrap spans, and re-rank
    with a sequence bonus.
- **Penalty ordering fix.**
  - Only apply units/style penalties when a line fails both appendix regex
    checks so legitimate headers are not suppressed.
- **Header-only index.**
  - Emit a `headers.ndjson` stream with `{id, page, text_norm, text_raw,
    start_char, end_char}` for each candidate header and fuse it with the main
    index via RRF.

## Acceptance tests

- **Appendix completeness:** Assert the final appendix slice contains all
  headers `A1`–`A8` in order; trigger neighbor rescue and re-ranking if the
  assertion fails.
- **Gap-penalty regression:** Inject a synthetic page missing A5 and verify the
  DP/CRF pass inserts the best candidate rather than jumping to A6.
- **Header-only retrieval:** Query "A6. Performance" against the header index
  and expect a top-3 hit even with Unicode noise.

Implementing just four items—span joiner, Viterbi gap-fill, header-only
indexing with RRF, and sequence-aware re-query—recovers A5/A6 in the
problematic document class while hardening the pipeline for future appendix
sections.
