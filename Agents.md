# agents.md — Header Detection Validation (Epf, Co.pdf)

> This document defines the **agents**, responsibilities, inputs/outputs, tunables, safeguards, and runbook for the real-world header detection test on **“Epf, Co.pdf”** using the new application features. It is designed to be repo-native, CI-ready, and **generalizable** (no document-specific hardcoding).

---

## 1) Objectives

* Load **Epf, Co.pdf** (case-insensitive, overridable path).
* Run the **UF-only + EFHG** header pipeline with one LLM vote.
* **Auto-tune** scoring weights/thresholds to recover the specified header tree (top-levels, subsections, and Appendix A1–A8 with robust gap detection for A5/A6).
* Emit **audit artifacts**, a **tuned config**, and a **pytest** that enforces ordered recovery with fuzzy matching.
* Enforce **No-Hardcoding Guardrail**: titles are never used to promote candidates—gold list is for **evaluation only**.

---

## 2) Agent Roster & Contracts

### 2.1 Orchestrator Agent

* **Role:** Coordinates the run; wires agents; manages config; surfaces final summary.
* **Inputs:** `pdf_path`, global config defaults, environment (`EPF_PDF_PATH`, logging level).
* **Outputs:** Summary block, paths to artifacts, exit code for CI.
* **Calls:** Preprocessor → UF Chunker → EFHG Scorer/Stitcher → LLM Voting → Sequence Repair → Evaluator → Tuner (optional loop) → Audit Writer → Unit Test Runner.

### 2.2 Preprocessor Agent

* **Role:** Robust text extraction & normalization with style tokens (size/weight/leading), OCR fallback.
* **Inputs:** PDF path.
* **Outputs:** `doc_decomp` (pages, lines, spans, styles, char offsets).
* **Success Criteria:** Deterministic tokenization; retains line breaks and style diffs.

### 2.3 UF Chunker Agent

* **Role:** Create **Ultrafine (UF)** microchunks from normalized text.
* **Inputs:** `doc_decomp`.
* **Outputs:** `uf_chunks: List[UFChunk]` with `{id, page, span_char, text, tokens}`.
* **Tunables:** `max_tokens=90`, `overlap=12`.

### 2.4 EFHG Scoring/Stitching Agent

* **Role:** Generate header **candidates** from UF chunks and **stitch** split headings.
* **Inputs:** `uf_chunks`, style metadata, punctuation graph, entropy profiles.
* **Outputs:** Candidate list with component scores + stitched spans.
* **Component Scores (weights are tunable):**

  * `w_regex` – generic numbered / Appendix / lettered schemas (regex families only).
  * `w_style` – font size/weight/leading/spacing contrasts vs body text.
  * `w_entropy` – boundary troughs/peaks neighborhood.
  * `w_graph` – line/paragraph breaks, title-case run length, sentence-end punctuation.
  * `w_fluid` – alignment confidence that text is header-like vs body.
  * `w_llm_vote` – LLM agreement score (from Voting Agent).
* **Promotion thresholds:** `t_header`, `t_subheader`.
* **Stitching thresholds:** `adjacency_weight`, `entropy_join_delta`, `style_cont_threshold`.

### 2.5 LLM Voting Agent

* **Role:** One pass on the **full normalized text** proposing potential headers; feeds **soft votes** to EFHG (no literals).
* **Inputs:** Full text, neutral prompt (“propose candidate headings and hierarchy”), **no gold strings**.
* **Outputs:** `llm_votes` keyed by candidate span.
* **Guardrail:** The vote cannot match against gold literals; it only provides **generic agreement** signals.

### 2.6 Sequence Repair Agent

* **Role:** Detect **schema gaps** and propose **non-literal** insertions/alignments.
* **Inputs:** Promoted headers/subheaders, candidate pool, numbering graph.
* **Outputs:** Repaired, ordered tree + `gaps.json`.
* **Schemas:**

  * Numeric/decimal: `^\d+(\.\d+)*\b`
  * Appendix: `^Appendix\s+[A-Z]\b`
  * Letter-numeric: `^[A-Z]\d+(\.\d+)*\b`
* **Tunables:** `hole_penalty`, `max_gap_span_pages`, `min_schema_support`.
* **A5/A6 Handling:** Recovered by **schema continuity + local evidence** only (no literal “A5” or “A6” branches).

### 2.7 Evaluator Agent

* **Role:** Compare detected tree to **gold list** for metrics and acceptance.
* **Inputs:** Detected tree, gold tree (evaluation only).
* **Outputs:** Precision/Recall/F1, Kendall-tau order distance, pass/fail flags.
* **Fuzzy Matching:**

  * Levenshtein ≤ **0.15** **or** token Jaccard ≥ **0.8**
  * **Strict monotonically increasing order** required.

### 2.8 Tuner Agent

* **Role:** **Coordinate ascent** over bounded grids to maximize macro-F1 with early stopping.
* **Inputs:** Initial config ranges, evaluator.
* **Outputs:** Tuned TOML config, grid report.
* **Ranges (defaults):**

  ```
  w_regex:[0.8,1.6], w_style:[0.6,1.4], w_entropy:[0.4,1.2],
  w_graph:[0.6,1.6], w_fluid:[0.4,1.2], w_llm_vote:[0.6,1.6],
  t_header:[0.55,0.80], t_subheader:[0.45,0.70],
  adjacency_weight:[0.4,1.2], entropy_join_delta:[0.08,0.22],
  style_cont_threshold:[0.55,0.85], hole_penalty:[0.2,0.6],
  max_gap_span_pages:{1,2,3}, min_schema_support:{2,3,4}
  ```

### 2.9 Audit Writer Agent

* **Role:** Persist artifacts for human and CI review.
* **Inputs:** Detected tree, scores, tuning history, gaps.
* **Outputs (under `./audit/epf_co/<timestamp>/`):**

  * `detected_headers.json`
  * `gaps.json`
  * `grid_search_report.json`
  * `audit.html`, `audit.md`
  * `results.junit.xml`
  * `tuned.header_detector.toml` (also copied to `./configs/tuned/header_detector.epf_co.toml`)

### 2.10 Test Runner Agent

* **Role:** Generate and execute a stable pytest.
* **Test File:** `tests/test_headers_epf_co.py`
* **Assertion:** Complete ordered recovery (top levels + subsections + Appendix A1–A8), fuzzy title match, monotonic order.
* **Failure Messages:** Identify missing or out-of-order nodes (name, expected index, detected index/page).

---

## 3) Config & Environment

* **PDF Resolution:**

  * Search order: `./docs`, `./samples`, `./data`, repo-wide fallback.
  * Override: `EPF_PDF_PATH=/abs/or/rel/path/to/Epf, Co.pdf`
* **Logging:** `LOG_LEVEL=DEBUG` recommended for tuning.
* **Determinism:** Set RNG seeds for tuner and any stochastic steps.

---

## 4) CLI & Make Targets

Prefer the unified runner. If missing, add `scripts/run_headers.py` and a Make alias.

### 4.1 Unified Runner (preferred)

```bash
python run.py headers detect \
  --pdf "$(python -c 'import os;print(os.getenv("EPF_PDF_PATH",""))')" \
  --tune --audit --verbose \
  --out ./audit/epf_co
```

### 4.2 Scripted Runner (fallback)

```bash
python scripts/run_headers.py \
  --pdf "Epf, Co.pdf" \
  --tune --audit --verbose \
  --out ./audit/epf_co
```

### 4.3 Make

```bash
make headers-epf-co
# Should: resolve PDF → run detect+tune → write artifacts → run pytest
```

---

## 5) Acceptance Criteria

* All **top-level sections (0–23)** present **in order**.
* All listed **subsections** present **in order**.
* **Appendix A1–A8** all present; **A5** and **A6** recovered via gap detection.
* No literal title promotion anywhere in detection/repair (guardrail must pass).
* **Macro-F1 ≥ 0.98** (target) with order distance minimal (ideally zero inversions).

---

## 6) Guardrails & Anti-Patterns

* ❌ **No hardcoded strings** (“A5”, “A6”, “Purpose & Background”, etc.) in detection paths.
* ❌ No regex that **only** matches the gold names.
* ✅ Only **generic** families: numbered (`^\d+(\.\d+)*`), Appendix (`^Appendix\s+[A-Z]`), letter-numeric (`^[A-Z]\d+(\.\d+)*`).
* ✅ A **Literals Sentinel** fails the run if any promotion path references an exact gold string.

---

## 7) Telemetry & Artifacts

* **Structured logs** at each gate:

  * Candidate creation → component scores → stitch decision → (de)promotion → sequence repair.
* **Key JSON Schemas:**

`detected_headers.json` (excerpt)

```json
{
  "document": "Epf, Co.pdf",
  "nodes": [
    {
      "level": 1,
      "text_raw": "0. Purpose & Background",
      "text_norm": "0 purpose & background",
      "page": 2,
      "score_total": 0.91,
      "scores": {
        "regex": 0.26, "style": 0.22, "entropy": 0.11,
        "graph": 0.14, "fluid": 0.08, "llm_vote": 0.10
      },
      "decision": "promote.header",
      "stitch": {"joined": false}
    }
  ]
}
```

`gaps.json` (excerpt)

```json
{
  "schemas": ["decimal", "appendix_letter_numeric"],
  "holes_filled": [
    {
      "expected": "A5",
      "evidence": {"left":"A4","right":"A6","style_sim":0.83,"graph_adj":0.78},
      "confidence": 0.86,
      "pages_spanned": 1
    }
  ]
}
```

---

## 8) Runbook

1. **Set PDF path (optional):**

   ```bash
   export EPF_PDF_PATH="/path/to/Epf, Co.pdf"
   ```
2. **Execute pipeline with tuning + audit:**

   ```bash
   make headers-epf-co
   ```
3. **Review outputs:**

   * Tuned config: `./configs/tuned/header_detector.epf_co.toml`
   * Audit pack: `./audit/epf_co/<timestamp>/...`
   * CI report: `./audit/epf_co/<timestamp>/results.junit.xml`
4. **Read summary in console:** Shows F1/precision/recall, A-series status (A5/A6), artifact paths, pytest result.

---

## 9) Failure Modes & Remedies

| Symptom               | Likely Cause                                                            | Remedy                                                                                                |
| --------------------- | ----------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| A5/A6 missing         | `min_schema_support` too high; `hole_penalty` too large; weak `w_graph` | Lower `min_schema_support`, reduce `hole_penalty`, increase `w_graph`, allow `max_gap_span_pages=2–3` |
| Many false headers    | Thresholds too low; `w_style` too high on noisy docs                    | Raise `t_header/t_subheader`, reduce `w_style`, increase `entropy_join_delta`                         |
| Out-of-order sections | Stitch too aggressive; weak graph                                       | Tighten `style_cont_threshold`, increase `adjacency_weight`, improve punctuation graph                |
| LLM vote dominates    | `w_llm_vote` too high                                                   | Reduce `w_llm_vote` within bounds                                                                     |
| Unit test flakiness   | Non-deterministic tuner                                                 | Fix RNG seeds; persist tuned config and re-run with `--no-tune`                                       |

---

## 10) Compliance with Gold List (Evaluation Only)

The gold hierarchy provided in the task is used **exclusively** by the Evaluator Agent to compute metrics and pass/fail. Detection and repair operate on **generic** signals and schemas.

---

## 11) Deliverables Checklist

* [ ] `scripts/run_headers.py` (if unified CLI missing)
* [ ] `make headers-epf-co`
* [ ] `configs/tuned/header_detector.epf_co.toml`
* [ ] `audit/epf_co/<timestamp>/{detected_headers.json,gaps.json,grid_search_report.json,audit.html,audit.md,results.junit.xml}`
* [ ] `tests/test_headers_epf_co.py`
* [ ] Orchestrator summary printed on completion

---

*This agents.md is scoped to the header-detection validation workflow and aligns with the new application’s unified run model, enhanced logging, UF-only chunking, EFHG scoring, LLM soft voting, aggressive sequence repair, and non-hardcoded tuning strategy.*
