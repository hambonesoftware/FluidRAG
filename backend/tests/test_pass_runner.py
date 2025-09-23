import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.pipeline.passes import runner


@pytest.fixture(autouse=True)
def configure_runner(monkeypatch):
    state = SimpleNamespace(filename="Doc.pdf", file_hash="hash123", provider=None, model=None)

    monkeypatch.setattr(runner, "get_state", lambda session_id: state)
    monkeypatch.setattr(runner, "ensure_chunks", lambda session_id: ["chunk-1"])
    monkeypatch.setattr(runner, "build_groups", lambda chunks: [["chunk-group"]])
    monkeypatch.setattr(
        runner,
        "resolve_pass_items",
        lambda payload: ([
            ("Mechanical", "prompt-mech"),
            ("Electrical", "prompt-elec"),
        ], []),
    )
    monkeypatch.setattr(runner, "resolve_pass_concurrency", lambda payload: 1)
    monkeypatch.setattr(runner, "resolve_pass_timeout", lambda payload: 30.0)
    monkeypatch.setattr(runner, "provider_default_model", lambda provider: "model-x")
    monkeypatch.setattr(runner, "env", lambda name, default=None: default)
    monkeypatch.setattr(runner, "PASS_STAGGER_SECONDS", 0)
    monkeypatch.setattr(
        runner,
        "export_pass_stage_snapshots",
        lambda session_id, pass_names, include_header=True: None,
    )
    monkeypatch.setattr(
        runner,
        "merge_pass_outputs",
        lambda outputs, req_id=None: {
            "rows": [
                row
                for name in sorted(outputs)
                for row in outputs[name].get("items", [])
            ],
            "problems": [],
        },
    )


def test_empty_cached_pass_triggers_rerun(monkeypatch):
    pass_cache = {
        "Mechanical": {"payload": {"items": [{"pass": "Mechanical", "cached": True}]}},
        "Electrical": {"payload": {"items": []}},
    }
    monkeypatch.setattr(runner, "get_pass_cache", lambda file_hash: pass_cache)

    executed = []

    async def fake_execute_pass(pass_name, *args, **kwargs):
        executed.append(pass_name)
        return (
            [{"pass": pass_name, "fresh": True}],
            [{"pass": pass_name, "debug": True}],
            [],
            [],
        )

    monkeypatch.setattr(runner, "execute_pass", fake_execute_pass)

    saved_payloads = {}

    def fake_save_pass_cache(file_hash, filename, pass_name, payload):
        saved_payloads[pass_name] = payload

    monkeypatch.setattr(runner, "save_pass_cache", fake_save_pass_cache)

    result = asyncio.run(runner.run_all_passes_async({"session_id": "sess-1"}))

    assert executed == ["Electrical"]
    assert saved_payloads == {
        "Electrical": {"items": [{"pass": "Electrical", "fresh": True}]}
    }
    assert result["cache"]["hits"] == ["Mechanical"]
    assert result["cache"]["misses"] == ["Electrical"]
    assert result["cache"]["stored_passes"] == ["Electrical", "Mechanical"]
    assert {row["pass"] for row in result["rows"]} == {"Mechanical", "Electrical"}


def test_force_refresh_runs_all_passes(monkeypatch):
    pass_cache = {
        "Mechanical": {"payload": {"items": [{"pass": "Mechanical", "cached": True}]}},
        "Electrical": {"payload": {"items": [{"pass": "Electrical", "cached": True}]}}
    }
    monkeypatch.setattr(runner, "get_pass_cache", lambda file_hash: pass_cache)

    executed = []

    async def fake_execute_pass(pass_name, *args, **kwargs):
        executed.append(pass_name)
        return (
            [{"pass": pass_name, "fresh": True}],
            [{"pass": pass_name, "debug": True}],
            [],
            [],
        )

    monkeypatch.setattr(runner, "execute_pass", fake_execute_pass)

    saved = []

    def fake_save_pass_cache(file_hash, filename, pass_name, payload):
        saved.append(pass_name)

    monkeypatch.setattr(runner, "save_pass_cache", fake_save_pass_cache)

    result = asyncio.run(runner.run_all_passes_async({
        "session_id": "sess-2",
        "force_refresh": True,
    }))

    assert set(executed) == {"Mechanical", "Electrical"}
    assert len(executed) == 2
    assert set(saved) == {"Mechanical", "Electrical"}
    assert result["cache"]["hits"] == []
    assert set(result["cache"]["misses"]) == {"Mechanical", "Electrical"}
    assert set(result["cache"]["stored_passes"]) == {"Mechanical", "Electrical"}
    assert {row["pass"] for row in result["rows"]} == {"Mechanical", "Electrical"}
