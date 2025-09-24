# ragx

Modular, context-aware retrieval-augmented generation components for FluidRAG experiments.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r ragx/requirements.txt
pip install -e ragx[develop]
```

## CLI usage

Build indexes:

```bash
python -m ragx.runners.build_indexes --doc ragx/tests/fixtures/tiny_doc.json --pass Mechanical --intent RETRIEVE
```

Run full pipeline:

```bash
python -m ragx.runners.run_pipeline --doc ragx/tests/fixtures/tiny_doc.json --pass Mechanical --intent RETRIEVE --query "mechanical weld thickness" --graph
```

Evaluate header detection:

```bash
python -m ragx.runners.eval_headers --doc ragx/tests/fixtures/tiny_doc.json --pass Mechanical
```

Evaluate retrieval improvements:

```bash
python -m ragx.runners.eval_retrieval --queries ragx/tests/fixtures/tiny_queries.yaml
```

## Extending profiles

Add or tune passes by editing `ragx/config/profiles.yaml`. Thresholds for segmentation, FLUID merging, HEP scoring, GraphRAG, and retrieval cascades are defined per pass.

## Consuming outputs

Each runner returns JSON structures that retain provenance (`anchors`, `pages`, `provenance`, `resolution`). Downstream extractors can join these with existing Mechanical/Electrical/Controls/Software/Project Management interpreters to consume ranked hits, meso parents, FLUID merges, HEP passages, and optional GraphRAG micrographs.
