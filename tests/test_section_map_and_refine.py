from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd

from tools.section_map_and_refine import detect_suspect, run_pipeline


class StubLLM:
    def __init__(self, response: dict) -> None:
        self._response = response
        self.calls = []

    def refine(self, **kwargs):  # type: ignore[override]
        self.calls.append(kwargs)
        return type("_Resp", (), {"content": json.dumps(self._response)})()


def write_stage(path: Path, chunks: list[dict]) -> None:
    path.write_text(json.dumps(chunks, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def test_section_mapping_populates_columns(tmp_path: Path) -> None:
    stage_dir = tmp_path / "stages"
    stage_dir.mkdir()
    write_stage(
        stage_dir / "Mechanical.json",
        [
            {
                "chunk_id": "chunk-001",
                "pass": "Mechanical",
                "section_id": "1.1",
                "section_title": "Scope",
                "text": "1.1 Scope description",
            },
            {
                "chunk_id": "chunk-002",
                "pass": "Mechanical",
                "section_id": "1.2",
                "section_title": "Performance",
                "text": "Maintain accuracy",
            },
        ],
    )

    results_path = tmp_path / "FluidRAG_results.csv"
    write_csv(
        results_path,
        [
            {
                "Specification": "Maintain accuracy",
                "Pass": "Mechanical",
                "SourceDoc": "spec.pdf",
                "ChunkID": "chunk-002",
            },
            {
                "Specification": "Scope description",
                "Pass": "Mechanical",
                "SourceDoc": "spec.pdf",
                "ChunkID": "",
            },
        ],
    )

    atomic_path = tmp_path / "requirements_atomic.csv"
    artifacts_dir = tmp_path / "artifacts"

    run_pipeline(
        stage_dir=stage_dir,
        in_csv=results_path,
        out_csv=results_path,
        atomic_csv=atomic_path,
        artifacts_dir=artifacts_dir,
        threshold=200,
        llm_client=None,
    )

    df = read_csv(results_path)
    assert str(df.loc[0, "(Sub)Section #"]) == "1.2"
    assert df.loc[0, "(Sub)Section Name"] == "Performance"
    assert str(df.loc[1, "(Sub)Section #"]) == "1.1"
    assert df.loc[1, "(Sub)Section Name"] == "Scope"

    expected_prefix = ["Specification", "(Sub)Section #", "(Sub)Section Name", "Pass", "SourceDoc", "ChunkID"]
    assert list(df.columns)[:6] == expected_prefix


def test_detect_suspect_flags_complex_specs() -> None:
    assert detect_suspect("Provide guarding; include alarm history")
    assert detect_suspect("Maintain 1.0 mm and 2.0 mm tolerances")
    assert not detect_suspect("Provide guarding with ISO 14120 compliance", threshold=200)


def test_refinement_replaces_parent_with_children(tmp_path: Path) -> None:
    stage_dir = tmp_path / "stages"
    stage_dir.mkdir()
    write_stage(
        stage_dir / "Controls.json",
        [
            {
                "chunk_id": "chunk-ctrl-001",
                "pass": "Controls",
                "section_id": "2.1",
                "section_title": "HMI",
                "text": "Recipes and alarms",
            }
        ],
    )

    results_path = tmp_path / "FluidRAG_results.csv"
    write_csv(
        results_path,
        [
            {
                "Specification": "Provide recipes and alarms; store history",
                "Pass": "Controls",
                "SourceDoc": "spec.pdf",
                "ChunkID": "chunk-ctrl-001",
            }
        ],
    )

    atomic_path = tmp_path / "requirements_atomic.csv"
    artifacts_dir = tmp_path / "artifacts"

    llm = StubLLM(
        {
            "parent_summary": "HMI manages recipes and alarms",
            "children": [
                {
                    "requirement_text": "HMI shall manage at least 50 recipes",
                    "req_type": "Utility",
                    "metric": "Recipe capacity",
                    "operator": ">=",
                    "target_value": 50,
                    "units": "",
                    "test_method": "DocReview",
                    "acceptance_window": "",
                    "tags": ["HMI"],
                },
                {
                    "requirement_text": "HMI shall retain alarm history for 30 days",
                    "req_type": "Utility",
                    "metric": "Alarm history duration",
                    "operator": ">=",
                    "target_value": 30,
                    "units": "",
                    "test_method": "FAT",
                    "acceptance_window": "",
                    "tags": ["Alarms"],
                },
            ],
        }
    )

    run_pipeline(
        stage_dir=stage_dir,
        in_csv=results_path,
        out_csv=results_path,
        atomic_csv=atomic_path,
        artifacts_dir=artifacts_dir,
        threshold=60,
        llm_client=llm,
    )

    df = read_csv(results_path)
    assert list(df["Atomicity"]) == ["parent", "atomic", "atomic"]
    assert df.loc[0, "ReqID"].startswith("S-2.1-001")
    assert df.loc[1, "ParentReqID"] == df.loc[0, "ReqID"]
    assert df.loc[1, "ReqID"].endswith("-a")
    assert pd.isna(df.loc[2, "Units"]) or df.loc[2, "Units"] == ""

    atomic_df = read_csv(atomic_path)
    assert list(atomic_df["Atomicity"]) == ["atomic", "atomic"]


def test_schema_guard_invalid_operator(tmp_path: Path) -> None:
    stage_dir = tmp_path / "stages"
    stage_dir.mkdir()
    write_stage(
        stage_dir / "Mechanical.json",
        [
            {
                "chunk_id": "chunk-001",
                "pass": "Mechanical",
                "section_id": "3.1",
                "section_title": "Alignment",
                "text": "Maintain alignment",
            }
        ],
    )

    results_path = tmp_path / "FluidRAG_results.csv"
    write_csv(
        results_path,
        [
            {
                "Specification": "Maintain alignment within 0.5 mm; include guard",
                "Pass": "Mechanical",
                "SourceDoc": "spec.pdf",
                "ChunkID": "chunk-001",
            }
        ],
    )

    atomic_path = tmp_path / "requirements_atomic.csv"
    artifacts_dir = tmp_path / "artifacts"

    class BadOperatorLLM:
        def refine(self, **kwargs):  # type: ignore[override]
            return type(
                "_Resp",
                (),
                {
                    "content": json.dumps(
                        {
                            "parent_summary": "Maintain alignment and guarding",
                            "children": [
                                {
                                    "requirement_text": "Alignment within 0.5 mm",
                                    "req_type": "Performance",
                                    "metric": "Alignment",
                                    "operator": ">",
                                    "target_value": 0.5,
                                    "units": "mm",
                                    "test_method": "Measurement",
                                    "acceptance_window": "",
                                    "tags": [],
                                }
                            ],
                        }
                    )
                },
            )()

    run_pipeline(
        stage_dir=stage_dir,
        in_csv=results_path,
        out_csv=results_path,
        atomic_csv=atomic_path,
        artifacts_dir=artifacts_dir,
        threshold=20,
        llm_client=BadOperatorLLM(),
    )

    df = read_csv(results_path)
    assert list(df["Atomicity"]) == ["suspect"]
    assert df.loc[0, "RefineError"].startswith("Invalid operator")

