"""Validate the enriched requirements register against the JSON schema."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pandas as pd
from jsonschema import Draft202012Validator

from .register_build import COLUMN_ORDER


def validate_register(df: pd.DataFrame, schema_path: Path) -> None:
    with schema_path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)

    validator = Draft202012Validator(schema)
    errors: List[str] = []
    for idx, row in enumerate(df.to_dict("records")):
        normalized = {key: (None if pd.isna(value) else value) for key, value in row.items()}
        for error in validator.iter_errors(normalized):
            req_id = row.get("ReqID", f"row-{idx}")
            errors.append(f"{req_id}: {error.message}")
    if errors:
        formatted = "\n".join(errors)
        raise ValueError(f"Register validation failed:\n{formatted}")

    # Ensure column order is preserved for downstream use.
    missing_columns = [column for column in COLUMN_ORDER if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Register is missing required columns: {missing_columns}")
