"""Atomicize specifications by splitting multi-clause rows into child requirements."""
from __future__ import annotations

from typing import Dict, List

import pandas as pd

from .register_build import COLUMN_ORDER, StageIndex
from .register_utils import (
    compute_anchor,
    detect_atomicity,
    extract_machine_fields,
    generate_req_id,
    infer_eval_bucket,
    infer_schedule_fields,
    infer_tags,
    split_spec_into_atoms,
)


def _parent_summary(spec: str) -> str:
    summary = spec.strip()
    if len(summary) > 140:
        summary = summary[:137].rstrip() + "…"
    return f"Composite requirement: {summary}"


def _normalize_parent(record: Dict[str, object]) -> Dict[str, object]:
    record = record.copy()
    record["Atomicity"] = "parent"
    record["Metric"] = ""
    record["Operator"] = ""
    record["TargetValue"] = None
    record["Units"] = ""
    record["TestMethod"] = "DocReview"
    record["AcceptanceWindow"] = ""
    record["Tags"] = record.get("Tags", "")
    return record


def atomicize_register(df: pd.DataFrame, stage_index: StageIndex) -> pd.DataFrame:
    current = df.copy()
    passes = 0
    while True:
        passes += 1
        new_records: List[Dict[str, object]] = []
        transformed = False
        for row in current.to_dict("records"):
            if row.get("Atomicity") != "suspect":
                new_records.append(row)
                continue

            transformed = True
            parent = _normalize_parent(row)
            parent["Specification"] = _parent_summary(row["Specification"])
            new_records.append(parent)

            context = stage_index.context(row.get("ChunkID", ""), window=2)
            atoms = split_spec_into_atoms(row["Specification"], context)
            if not atoms:
                atoms = [row["Specification"]]

            base_section = row.get("SectionID")
            for idx, atom in enumerate(atoms):
                child = row.copy()
                child["Specification"] = atom.strip()
                suffix = f"-{chr(ord('A') + idx)}"
                child["ReqID"] = generate_req_id(base_section, child["Specification"], suffix=suffix)
                child["Anchor"] = compute_anchor(child["Specification"])
                child["ParentReqID"] = parent["ReqID"]
                machine = extract_machine_fields(child["Specification"], child["Pass"])
                child["ReqType"] = machine["ReqType"]
                child["Metric"] = machine["Metric"]
                child["Operator"] = machine["Operator"]
                child["TargetValue"] = machine["TargetValue"]
                child["Units"] = machine["Units"]
                child["TestMethod"] = machine["TestMethod"]
                child["AcceptanceWindow"] = machine["AcceptanceWindow"]
                child["EvalBucket"] = infer_eval_bucket(child["ReqType"])
                child["Tags"] = infer_tags(child["Specification"])
                milestone, week, payment = infer_schedule_fields(child["Specification"], child["ReqType"])
                if milestone:
                    child["Milestone"] = milestone
                if week is not None:
                    child["Week"] = week
                if payment:
                    child["PaymentTerm"] = payment
                child["Atomicity"] = detect_atomicity(child["Specification"])
                new_records.append(child)

        current = pd.DataFrame.from_records(new_records, columns=COLUMN_ORDER)
        if not transformed or passes >= 4:
            break
    if (current["Atomicity"] == "suspect").any():
        # Force final cleanup by marking remaining rows as atomic to avoid infinite loops
        current.loc[current["Atomicity"] == "suspect", "Atomicity"] = "atomic"
    return current.sort_values(["Pass", "SectionID", "ReqID"]).reset_index(drop=True)
