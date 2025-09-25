# ragx

Modular, context-aware retrieval-augmented generation components for FluidRAG experiments.

## Installation

The toolkit targets Python 3.10+. Create a virtual environment and install the light base requirements (PyYAML only by default). Optional evaluation tooling (pytest) is exposed through the `develop` extra.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r ragx/requirements.txt
# Optional developer extras (tests, linting hooks)
pip install -e ragx[develop]
```

> ℹ️  Heavy dependencies (sentence encoders, graph packages) are optional. Add them to your environment as needed and gate usage via the runner flags.

## CLI usage

Build per-pass indexes (segmentation + FLUID merges cached under `artifacts/`):

```bash
python -m ragx.runners.build_indexes \
  --doc ragx/tests/fixtures/tiny_doc.json \
  --pass Mechanical \
  --intent RETRIEVE
```

Run the full pipeline end-to-end (segmentation → FLUID → HEP → retrieval → optional GraphRAG):

```bash
python -m ragx.runners.run_pipeline \
  --doc ragx/tests/fixtures/tiny_doc.json \
  --pass Mechanical \
  --intent RETRIEVE \
  --query "mechanical weld thickness" \
  --graph    # omit to skip GraphRAG
```

Evaluate header detection quality with adaptive IoU scoring:

```bash
python -m ragx.runners.eval_headers --doc ragx/tests/fixtures/tiny_doc.json --pass Mechanical
```

Evaluate retrieval cascades against the tiny fixtures (reports average nDCG/Recall and deltas vs sparse baseline):

```bash
python -m ragx.runners.eval_retrieval --queries ragx/tests/fixtures/tiny_queries.yaml
```

## Extending profiles

Each pass (Mechanical, Electrical, Controls, Software, Project Management) is configured in `ragx/config/profiles.yaml`. Update the segmentation weights, FLUID similarity thresholds, HEP evidence weighting, GraphRAG vocabularies, and retrieval cascades per intent in that file. Bumping the YAML automatically changes the context `version` hash so downstream caches invalidate cleanly.

To add a new pass, copy an existing block, adjust the signal weights, boosts, and hints, then point `runners/run_pipeline.py` (or your orchestration layer) at the new pass name.

## Consuming outputs

All pipeline stages emit JSON with consistent provenance:

- `anchors`, `pages`, and `provenance` carry section IDs and page ranges end-to-end (meso sections, FLUID aggregates, HEP passages, retrieval hits, GraphRAG communities).
- Retrieval hits now include `stage_tag` plus per-stage scores so downstream rank fusion can reason about cascade contributions.

Downstream Mechanical/Electrical/Controls/Software/PM extractors can ingest these structures directly—join on `provenance` identifiers to recover meso parents, or use the validator to enforce pass/domain guardrails before persisting results.
