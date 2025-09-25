from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from tools import register_atomicize, register_build, register_metrics, register_validate


def _root_path() -> Path:
    return Path(__file__).resolve().parents[1]


def test_register_pipeline_end_to_end(tmp_path: Path) -> None:
    stage_dir = tmp_path / "stages"
    stage_dir.mkdir()
    stage_payload = [
        {
            "chunk_id": "chunk-001",
            "pass": "Controls",
            "section_id": "1.1",
            "section_title": "Controls Overview",
            "header_anchor": "controls-overview",
            "page_start": 5,
            "page_end": 5,
            "text": "System shall provide: \n• Recipe management for 40 recipes.\n• Alarm history for 21 days.",
        },
        {
            "chunk_id": "chunk-002",
            "pass": "Mechanical",
            "section_id": "1.2",
            "section_title": "Mechanical Performance",
            "header_anchor": "mechanical-performance",
            "page_start": 6,
            "page_end": 6,
            "text": "Maintain alignment within ±0.25 mm and include guarding per ISO 14120.",
        },
    ]
    with (stage_dir / "stage.json").open("w", encoding="utf-8") as handle:
        json.dump(stage_payload, handle)

    raw_rows = [
        {
            "Specification": "System shall provide recipe management for 40 recipes and alarm history for 21 days.",
            "Pass": "Controls",
            "SourceDoc": "Spec.pdf",
            "ChunkID": "chunk-001",
        },
        {
            "Specification": "Maintain alignment within 0.25 mm and include guarding per ISO 14120.",
            "Pass": "Mechanical",
            "SourceDoc": "Spec.pdf",
            "ChunkID": "chunk-002",
        },
        {
            "Specification": "FAT shall occur in week 12 with customer witness.",
            "Pass": "Project Management",
            "SourceDoc": "Schedule.pdf",
            "ChunkID": "chunk-002",
        },
    ]
    raw_df = pd.DataFrame(raw_rows)
    raw_path = tmp_path / "raw.csv"
    raw_df.to_csv(raw_path, index=False)

    stage_index = register_build.load_stage_index(stage_dir)
    base_df = register_build.build_register(stage_index, raw_path)
    # First row should be suspect because of multi-clause spec
    assert "suspect" in base_df["Atomicity"].values
    assert base_df.loc[0, "SectionID"] == "1.1"

    atomic_df = register_atomicize.atomicize_register(base_df, stage_index)
    assert "suspect" not in atomic_df["Atomicity"].values
    parent_rows = atomic_df[atomic_df["Atomicity"] == "parent"]
    assert not parent_rows.empty
    for _, parent_row in parent_rows.iterrows():
        child_rows = atomic_df[atomic_df["ParentReqID"] == parent_row["ReqID"]]
        assert not child_rows.empty

    schema_path = _root_path() / "schemas" / "requirements_register.schema.json"
    register_validate.validate_register(atomic_df, schema_path)

    metrics = register_metrics.bucket_metrics(atomic_df)
    assert metrics["buckets"]
    matrix = register_metrics.build_compliance_matrix(atomic_df)
    assert not matrix.empty
    assert set(["ReqID", "Requirement", "Pass", "SectionID", "TestMethod", "Compliance (Y/N/NA)"]).issubset(matrix.columns)

    schedule_rows = atomic_df[atomic_df["ReqType"] == "Schedule"]
    assert not schedule_rows.empty
    assert schedule_rows.iloc[0]["Week"] == 12
