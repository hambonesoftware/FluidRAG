"""Unit tests covering retrieval pass helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ...config import get_settings
from ...contracts.passes import PassResult
from ...services.rag_pass_service import run_all
from ...services.rag_pass_service.packages.compose.context import compose_window
from ...services.rag_pass_service.packages.emit.results import write_pass_results
from ...services.rag_pass_service.packages.retrieval import retrieve_ranked

pytestmark = pytest.mark.phase6


@pytest.fixture(autouse=True)
def _configure_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLUIDRAG_OFFLINE", "true")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _sample_chunks() -> list[dict[str, object]]:
    return [
        {
            "chunk_id": "doc:c1",
            "text": "Torque requirement is 50 Nm with 200 RPM limit.",
            "token_count": 9,
            "sentence_start": 0,
            "sentence_end": 0,
            "header_path": "Mechanics/Drive",
        },
        {
            "chunk_id": "doc:c2",
            "text": "The controller monitors pressure and temperature sensors.",
            "token_count": 9,
            "sentence_start": 1,
            "sentence_end": 1,
            "header_path": "Controls/Safety",
        },
        {
            "chunk_id": "doc:c3",
            "text": "Project timeline shows integration milestone at week 12.",
            "token_count": 10,
            "sentence_start": 2,
            "sentence_end": 2,
            "header_path": "PM/Schedule",
        },
    ]


def test_test_passes() -> None:
    """Unit test placeholder."""

    ranked = retrieve_ranked(_sample_chunks(), domain="mechanical")
    assert ranked, "ranked results should not be empty"


def test_hybrid_retrieval_ranking() -> None:
    """Validate BM25+dense+physics re-ranking on sample corpus."""

    ranked = retrieve_ranked(_sample_chunks(), domain="mechanical")
    assert ranked[0]["chunk_id"] == "doc:c1"
    assert ranked[0]["total_score"] >= ranked[-1]["total_score"]


def test_hybrid_retrieval_emits_physics_scores_sorted() -> None:
    """Ranked results expose physics scores and are sorted by total."""

    ranked = retrieve_ranked(_sample_chunks(), domain="mechanical")
    totals = [item["total_score"] for item in ranked]
    assert totals == sorted(totals, reverse=True)
    for item in ranked:
        assert "flow_score" in item and item["flow_score"] >= 0
        assert "energy_score" in item and item["energy_score"] >= 0
        assert "graph_score" in item and item["graph_score"] >= 0


def test_write_pass_results_persists_payload(tmp_path: Path) -> None:
    ranked = retrieve_ranked(_sample_chunks(), domain="controls")
    answer = {
        "content": "Answer",
        "context": "Context",
        "prompt": {"system": "s", "user": "u"},
    }
    path = write_pass_results("doc", "controls", answer, ranked)
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    assert payload["doc_id"] == "doc"
    assert payload["pass_name"] == "controls"


def test_run_all_emits_all_passes(tmp_path: Path) -> None:
    chunks_path = tmp_path / "header_chunks.jsonl"
    lines = [json.dumps(row) for row in _sample_chunks()]
    chunks_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    jobs = run_all("doc", str(chunks_path))
    assert set(jobs.passes.keys()) == {
        "mechanical",
        "electrical",
        "software",
        "controls",
        "project_mgmt",
    }
    for artifact in jobs.passes.values():
        assert Path(artifact).exists()


def test_run_all_outputs_validate_schema_and_content(tmp_path: Path) -> None:
    """Generated pass artifacts validate against schema and retain context."""

    chunks_path = tmp_path / "header_chunks.jsonl"
    lines = [json.dumps(row) for row in _sample_chunks()]
    chunks_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    jobs = run_all("doc", str(chunks_path))
    manifest_data = json.loads(Path(jobs.manifest_path).read_text(encoding="utf-8"))
    assert set(manifest_data["passes"].keys()) == {
        "mechanical",
        "electrical",
        "software",
        "controls",
        "project_mgmt",
    }

    for name, artifact in manifest_data["passes"].items():
        payload = Path(artifact).read_text(encoding="utf-8")
        result = PassResult.model_validate_json(payload)
        assert result.pass_name == name
        assert result.doc_id == "doc"
        assert result.answer, "answers should not be empty"
        assert result.context, "context window should be present"
        assert result.retrieval, "retrieval trace should be populated"
        assert result.citations, "citations should include supporting chunks"
        for citation in result.citations:
            assert citation.chunk_id.startswith(
                "doc:"
            ), "citation chunk id should include doc prefix"
            assert citation.header_path, "citation header path is required"
        top_header = result.retrieval[0].header_path
        if top_header:
            assert top_header in result.context
        preview = result.retrieval[0].text_preview.strip()
        if preview:
            assert preview in result.answer


def test_compose_window_dedupes_and_honors_budget() -> None:
    """Context composer removes duplicates and respects token ceiling."""

    ranked = [
        {
            "chunk_id": "doc:c1",
            "text": "Alpha beta gamma",
            "header_path": "Mechanics/Drive",
        },
        {
            "chunk_id": "doc:c1",
            "text": "Duplicate chunk should not appear",
            "header_path": "Mechanics/Drive",
        },
        {
            "chunk_id": "doc:c2",
            "text": "Delta epsilon zeta eta theta",
            "header_path": "Controls/Safety",
        },
    ]
    window = compose_window(ranked, budget_tokens=5)
    assert window.count("Mechanics/Drive") == 1
    assert "Duplicate" not in window
    assert "Controls/Safety" not in window
    segments = window.split("\n\n")
    assert segments == ["[Mechanics/Drive] Alpha beta gamma"]
