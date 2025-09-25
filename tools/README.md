# Requirements Register Toolkit

This folder contains a lightweight toolchain for generating an atomic requirements register from the FluidRAG stage JSON files and the latest CSV export.

## CLI usage

```bash
python -m tools.register_cli \
  --stages data/stages \
  --raw data/output/FluidRAG_results.csv \
  --out data/output/requirements_register.csv \
  --metrics data/output/requirements_register_metrics.json \
  --matrix data/output/compliance_matrix.csv
```

The CLI runs the full pipeline:

1. **Build** – merges stage metadata with the raw CSV, populating section/page and traceability fields.
2. **Atomicize** – splits multi-clause specifications into child requirements and links them to a parent row.
3. **Validate** – checks the enriched rows against `schemas/requirements_register.schema.json` to ensure schema compliance.
4. **Metrics** – emits coverage summaries (`requirements_register_metrics.json`) and a compliance matrix (`compliance_matrix.csv`).

The script fails fast if schema validation does not pass so that noisy rows can be corrected before export.

## Development

Run the unit tests with:

```bash
pytest -q tests/test_register_pipeline.py
```

The test suite exercises the parsing, atomicisation, validation, and metrics stages end-to-end.
