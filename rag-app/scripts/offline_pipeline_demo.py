"""Utility helpers for running the pipeline orchestrator offline."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import httpx


@dataclass(frozen=True)
class PipelineRunResult:
    """Aggregate payload returned by the offline pipeline demo."""

    doc_id: str
    status_payload: dict[str, Any]
    results_payload: dict[str, Any]


def _ensure_response_ok(response: httpx.Response, *, context: str) -> None:
    """Normalize HTTPX error handling for demo requests."""

    if response.status_code >= 400:
        raise RuntimeError(f"{context} failed with status {response.status_code}")
    try:
        request = response.request
    except RuntimeError:
        request = None
    if request is None:
        return
    response.raise_for_status()


def trigger_pipeline_run(client: httpx.Client, base_url: str, file_name: str) -> str:
    """Trigger the orchestrator run endpoint and return the document id."""

    response = client.post(f"{base_url}/pipeline/run", json={"file_name": file_name})
    _ensure_response_ok(response, context="pipeline run")
    payload = response.json()
    doc_id = payload.get("doc_id")
    if not isinstance(doc_id, str) or not doc_id:
        raise RuntimeError("backend response missing doc_id")
    return doc_id


def poll_pipeline_status(
    client: httpx.Client,
    base_url: str,
    doc_id: str,
    *,
    interval: float = 1.0,
    timeout: float = 60.0,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Poll the pipeline status endpoint until completion."""

    deadline = monotonic() + timeout
    last_error: str | None = None
    while True:
        try:
            response = client.get(f"{base_url}/pipeline/status/{doc_id}")
            if response.status_code == 404:
                last_error = "document not ready"
            else:
                _ensure_response_ok(response, context="pipeline status")
                status_payload = response.json()
                audit = status_payload.get("pipeline_audit", {})
                pipeline_meta = audit.get("pipeline") if isinstance(audit, dict) else None
                if isinstance(pipeline_meta, dict) and pipeline_meta.get("status") == "ok":
                    return status_payload
                last_error = "pipeline incomplete"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        if monotonic() >= deadline:
            detail = last_error or "pipeline status polling timed out"
            raise TimeoutError(detail)
        sleep(interval)


def fetch_pipeline_results(client: httpx.Client, base_url: str, doc_id: str) -> dict[str, Any]:
    """Fetch pipeline results for the document."""

    response = client.get(f"{base_url}/pipeline/results/{doc_id}")
    _ensure_response_ok(response, context="pipeline results")
    return response.json()


def run_demo(
    document_path: Path,
    *,
    base_url: str = "http://127.0.0.1:8000",
    poll_interval: float = 1.0,
    timeout: float = 60.0,
    client_factory: Callable[[float], httpx.Client] | None = None,
) -> PipelineRunResult:
    """Run the offline pipeline demo using the orchestrator endpoints."""

    if not document_path.exists():
        raise FileNotFoundError(f"document not found: {document_path}")

    factory = client_factory or (lambda duration: httpx.Client(timeout=duration))
    with factory(timeout + 5) as client:
        doc_id = trigger_pipeline_run(client, base_url, str(document_path))
        status_payload = poll_pipeline_status(
            client,
            base_url,
            doc_id,
            interval=poll_interval,
            timeout=timeout,
        )
        results_payload = fetch_pipeline_results(client, base_url, doc_id)
    return PipelineRunResult(doc_id=doc_id, status_payload=status_payload, results_payload=results_payload)


def run_cli(args: Sequence[str] | None = None) -> int:
    """Entry point for the demo when executed as a script."""

    parser = argparse.ArgumentParser(description="Run the offline pipeline demo via HTTP")
    parser.add_argument("document", type=Path, help="Path to the source document")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL for the orchestrator backend.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Polling interval in seconds (default: 1.0).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Polling timeout in seconds (default: 60).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the aggregated payload as JSON.",
    )

    parsed = parser.parse_args(list(args) if args is not None else None)
    result = run_demo(
        parsed.document,
        base_url=parsed.base_url,
        poll_interval=parsed.interval,
        timeout=parsed.timeout,
    )

    if parsed.json:
        print(
            json.dumps(
                {
                    "doc_id": result.doc_id,
                    "status": result.status_payload,
                    "results": result.results_payload,
                },
                indent=2,
            )
        )
    else:
        print(f"Pipeline completed for {result.doc_id}")
        print("Status summary:")
        print(json.dumps(result.status_payload, indent=2))
        print("Results summary:")
        print(json.dumps(result.results_payload, indent=2))
    return 0


def main() -> None:
    """CLI hook for ``python scripts/offline_pipeline_demo.py``."""

    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()
