"""Compute evaluation metrics and compliance matrices for the requirements register."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

import pandas as pd

EVAL_BUCKET_WEIGHTS: Dict[str, int] = {
    "Performance20": 20,
    "Maintenance10": 10,
    "Safety15": 15,
    "Energy10": 10,
    "Commercial20": 20,
    "Schedule15": 15,
    "Documentation5": 5,
}


def bucket_metrics(df: pd.DataFrame) -> Dict[str, object]:
    summary: List[Dict[str, object]] = []
    for bucket, weight in EVAL_BUCKET_WEIGHTS.items():
        bucket_rows = df[df["EvalBucket"] == bucket]
        coverage_ratio = len(bucket_rows) / max(weight, 1)
        coverage_percent = round(min(coverage_ratio * 100, 100.0), 1)
        risk = "low"
        if coverage_percent < 50:
            risk = "high"
        elif coverage_percent < 100:
            risk = "medium"
        summary.append(
            {
                "bucket": bucket,
                "weight": weight,
                "requirements": int(len(bucket_rows)),
                "coverage_percent": coverage_percent,
                "risk": risk,
            }
        )
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "generated_at": generated_at,
        "total_requirements": int(len(df)),
        "buckets": summary,
    }


def build_compliance_matrix(df: pd.DataFrame) -> pd.DataFrame:
    records: List[Dict[str, object]] = []
    for row in df.to_dict("records"):
        compliance = "NA"
        if row.get("ReqType") in {"Performance", "Safety"} and row.get("Operator"):
            compliance = "N"
        records.append(
            {
                "ReqID": row.get("ReqID"),
                "Requirement": row.get("Specification"),
                "Pass": row.get("Pass"),
                "SectionID": row.get("SectionID"),
                "TestMethod": row.get("TestMethod"),
                "Compliance (Y/N/NA)": compliance,
                "EvidenceRef": "",
            }
        )
    return pd.DataFrame.from_records(records)
