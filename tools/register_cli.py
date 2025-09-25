"""Command line interface for building the atomic requirements register."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from . import register_atomicize, register_build, register_metrics, register_validate


def run_pipeline(
    stage_dir: Path,
    raw_csv: Path,
    output_csv: Path,
    metrics_path: Path,
    matrix_path: Path,
    schema_path: Optional[Path] = None,
) -> None:
    stage_index = register_build.load_stage_index(stage_dir)
    if not list(stage_index.chunks):
        raise FileNotFoundError(f"No stage JSON files found in {stage_dir}")

    register_df = register_build.build_register(stage_index, raw_csv)
    atomic_df = register_atomicize.atomicize_register(register_df, stage_index)

    schema = schema_path or Path("schemas/requirements_register.schema.json")
    register_validate.validate_register(atomic_df, schema)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    matrix_path.parent.mkdir(parents=True, exist_ok=True)

    atomic_df.to_csv(output_csv, index=False)

    metrics = register_metrics.bucket_metrics(atomic_df)
    with metrics_path.open("w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2)
        handle.write("\n")

    compliance_df = register_metrics.build_compliance_matrix(atomic_df)
    compliance_df.to_csv(matrix_path, index=False)


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Generate the FluidRAG requirements register")
    parser.add_argument("--stages", type=Path, required=True, help="Directory containing stage JSON files")
    parser.add_argument("--raw", type=Path, required=True, help="Raw CSV exported from the current pipeline")
    parser.add_argument("--out", type=Path, required=True, help="Output CSV path for the enriched register")
    parser.add_argument("--metrics", type=Path, required=True, help="Path to write evaluation metrics JSON")
    parser.add_argument("--matrix", type=Path, required=True, help="Path to write the compliance matrix CSV")
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("schemas/requirements_register.schema.json"),
        help="Optional schema path used for validation",
    )
    args = parser.parse_args(argv)

    run_pipeline(args.stages, args.raw, args.out, args.metrics, args.matrix, schema_path=args.schema)


if __name__ == "__main__":
    main()
