# Appendix Header Recovery Playbook

This note collects production-ready techniques for surfacing missing appendix
headers—specifically **A5** and **A6** in RFQ-style documents—when PDF
segmentation or typography is unreliable. Each technique maps to an existing
stage in the FluidRAG pipeline so it can be enabled incrementally.

## Pre-ingest (make the text exist the way you need)

1. **Redundant line segmentation ensemble (vote & merge).**
   - Run multiple segmentation strategies (e.g., PDF text layout, OCR, and a
     punctuation-aware splitter).
   - Union their header detections using normalized text and allow "votes" for
     lines that resemble `^A[56]\.` within ±3 lines of the surrounding
     appendix headers.

2. **Unicode and glyph normalization.**
   - Normalize byte-level variants of spaces and dots before regex checks.
   - Strip zero-width characters and map confusable glyphs (Latin `A` vs.
     Cyrillic `А`, etc.).

3. **Header-first hard splits.**
   - Treat patterns such as `^\d+\)` and `^A\d+\.` as hard record boundaries
     so a wrapped appendix title always starts a fresh line.

## Header detection (turn "likely" into "certain")

4. **Sequence model for header tagging.**
   - Train a lightweight tagger (HMM, CRF, or tiny BiLSTM) over page-level
     sequences with features you already capture (font size, bold state,
     caps ratio, regex hit, indent).
   - Decode with Viterbi and enforce monotonic transitions `A3→A4→A5→A6→A7`.

5. **Expected-neighbor rescoring.**
   - Build a finite-state graph over appendix states and penalize missing
     transitions during inference to nudge borderline lines into A5/A6 when
     the gap would otherwise be skipped.

6. **Span-joiner with soft unwrap.**
   - If the tokenized header is followed by a very short line, join the pair
     and rescore as a single span. This repairs PDFs that split "A5." and the
     header title across lines.

## Indexing (so retrieval can actually fetch them)

7. **Header shards and multi-granularity indexing.**
   - Emit dedicated appendix header shards (≈60–120 tokens) alongside the
     standard micro- and macro-chunks.
   - Fuse retrieval results using Reciprocal Rank Fusion so a header-only hit
     can rescue a miss from the longer chunks.

8. **ColBERT late-interaction scoring for headers.**
   - Train or fine-tune a ColBERT encoder on short appendix header strings so
     similarity search remains robust to layout noise and glyph swaps.

## Retrieval (at question time)

9. **Sequence-aware re-query.**
   - When retrieval yields adjacent appendix headers but skips A5 or A6,
     auto-issue a follow-up query constrained to the same page window and the
     normalized patterns `^A[56]` or `A 5`/`A 6` variants.

10. **GraphRAG over a document outline.**
    - Construct a lightweight outline graph with edges between sequential
      appendix nodes and always include direct neighbors in the retrieved set.

## Post-selection (after candidate scoring)

11. **Monotone dynamic-programming repair.**
    - Apply a DP pass that maximizes the score of a contiguous appendix
      sequence while penalizing skipped states; borderline candidates for A5
      or A6 are promoted whenever they avoid a gap.

12. **Self-consistency multi-decode.**
    - Run a small ensemble of LLM decodes over the appendix region only.
    - If the majority outputs contain A5/A6 but the final set does not, trigger
      a focused re-scan using the techniques above.

## Production drop-ins

- **Neighbor rescue micro-pass.**
  - If `{A3, A4, A7, A8}` are present but `{A5, A6}` are not, rescan ±10 lines
    around the gap with normalization plus soft unwrap, then re-rank with a
    sequence bonus.
- **Penalty ordering fix.**
  - Only apply units/style penalties when a line fails both appendix regex
    checks so legitimate headers are not suppressed.
- **Header-only index.**
  - Emit a `headers.ndjson` stream with `{id, page, text_norm, text_raw,
    start_char, end_char}` for each candidate header and fuse it with the main
    index during retrieval.

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
