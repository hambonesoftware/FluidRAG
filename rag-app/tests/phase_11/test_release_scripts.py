"""Tests for Phase 11 release helpers and demos."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from scripts import offline_pipeline_demo as pipeline_demo
from scripts import release_checklist


class FakeClock:
    """Minimal clock helper for controlling poll timings in tests."""

    def __init__(self) -> None:
        self.value = 0.0

    def sleep(self, seconds: float) -> None:
        self.value += seconds

    def monotonic(self) -> float:
        return self.value


def test_has_heading_detects_markdown_heading(tmp_path: Path) -> None:
    doc = tmp_path / "README.md"
    doc.write_text("## Quickstart\ncontent", encoding="utf-8")
    assert release_checklist.has_heading(doc, "Quickstart") is True
    assert release_checklist.has_heading(doc, "Troubleshooting") is False


def test_discover_release_artifacts_handles_missing(tmp_path: Path) -> None:
    (tmp_path / "reports").mkdir()
    checks = release_checklist.discover_release_artifacts(tmp_path)
    statuses = {check.name: check for check in checks}
    assert statuses["README"].status is False
    assert "README missing" in statuses["README"].detail
    assert statuses["Changelog"].status is False
    assert statuses["Environment Template"].status is False
    assert statuses["Outcome Report"].status is False
    assert statuses["Backlog"].status is False
    assert statuses["Demo Script"].status is False


def test_release_checklist_passes_for_repo_root() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    checks = release_checklist.discover_release_artifacts(repo_root)
    assert checks, "Expected checklist entries"
    assert all(check.status for check in checks), release_checklist.render_summary(
        checks
    )


def test_release_cli_json_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "README.md").write_text(
        "## Quickstart\n## Environment Setup\n## Troubleshooting", encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text("## Phase 11", encoding="utf-8")
    (tmp_path / ".env.example").write_text("", encoding="utf-8")
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "phase_11_outcome.md").write_text("done", encoding="utf-8")
    (reports / "post_phase_backlog.md").write_text("backlog", encoding="utf-8")
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "offline_pipeline_demo.py").write_text("", encoding="utf-8")

    exit_code = release_checklist.run_cli(["--root", str(tmp_path), "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert all(item["status"] for item in payload)


def test_trigger_pipeline_run_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/pipeline/run")
        return httpx.Response(200, json={"doc_id": "doc-123"})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        doc_id = pipeline_demo.trigger_pipeline_run(client, "http://test", "sample.pdf")
    assert doc_id == "doc-123"


def test_trigger_pipeline_run_missing_doc_id() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(RuntimeError, match="doc_id"):
            pipeline_demo.trigger_pipeline_run(client, "http://test", "sample.pdf")


def test_poll_pipeline_status_until_complete() -> None:
    clock = FakeClock()
    calls: dict[str, int] = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(404)
        if calls["count"] == 2:
            return httpx.Response(
                200, json={"pipeline_audit": {"pipeline": {"status": "running"}}}
            )
        return httpx.Response(
            200, json={"pipeline_audit": {"pipeline": {"status": "ok"}}}
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        payload = pipeline_demo.poll_pipeline_status(
            client,
            "http://test",
            "doc-123",
            interval=0.1,
            timeout=5.0,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )
    assert payload["pipeline_audit"]["pipeline"]["status"] == "ok"
    assert calls["count"] >= 3


def test_poll_pipeline_status_times_out() -> None:
    clock = FakeClock()

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        with pytest.raises(TimeoutError, match="document not ready"):
            pipeline_demo.poll_pipeline_status(
                client,
                "http://test",
                "doc-404",
                interval=0.1,
                timeout=0.3,
                sleep=clock.sleep,
                monotonic=clock.monotonic,
            )


def test_run_demo_uses_custom_client_factory(tmp_path: Path) -> None:
    document = tmp_path / "sample.pdf"
    document.write_text("data", encoding="utf-8")

    class StubClient:
        def __init__(self) -> None:
            self.requests: list[tuple[str, str]] = []

        def __enter__(self) -> StubClient:
            return self

        def __exit__(self, *exc: Any) -> None:
            return None

        def post(self, url: str, json: dict[str, Any]) -> httpx.Response:
            self.requests.append(("POST", url))
            return httpx.Response(200, json={"doc_id": "doc-321"})

        def get(self, url: str) -> httpx.Response:
            self.requests.append(("GET", url))
            if url.endswith("/status/doc-321"):
                return httpx.Response(
                    200, json={"pipeline_audit": {"pipeline": {"status": "ok"}}}
                )
            return httpx.Response(200, json={"passes": {}})

    def factory(_: float) -> StubClient:
        return StubClient()

    result = pipeline_demo.run_demo(
        document,
        base_url="http://test",
        poll_interval=0.1,
        timeout=1.0,
        client_factory=factory,
    )
    assert result.doc_id == "doc-321"
    assert result.results_payload["passes"] == {}


def test_fetch_pipeline_results_success() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"passes": {"summary": "ok"}})
    )
    with httpx.Client(transport=transport) as client:
        payload = pipeline_demo.fetch_pipeline_results(client, "http://test", "doc-1")
    assert payload["passes"]["summary"] == "ok"
