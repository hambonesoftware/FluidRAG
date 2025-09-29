"""Tests for audit record helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.util.audit import stage_record
from backend.app.util.logging import correlation_context


def test_stage_record_uses_correlation_and_duration() -> None:
    started = datetime.now(tz=timezone.utc) - timedelta(milliseconds=25)
    ended = datetime.now(tz=timezone.utc)
    with correlation_context("audit-123"):
        record = stage_record(
            stage="demo",
            status="ok",
            started_at=started,
            ended_at=ended,
            extra="value",
        )
    assert record["stage"] == "demo"
    assert record["status"] == "ok"
    assert record["correlation_id"] == "audit-123"
    assert record["extra"] == "value"
    assert 20 <= record["duration_ms"] <= 40


def test_stage_record_accepts_explicit_duration() -> None:
    with correlation_context(None):
        record = stage_record(stage="demo", status="error", duration_ms=12.345)
    assert record["duration_ms"] == pytest.approx(12.345, rel=1e-3)
    assert record["status"] == "error"
