"""Tests for retry utilities."""
from __future__ import annotations

import pytest

from backend.app.util.errors import RetryExhaustedError
from backend.app.util.retry import CircuitBreaker, RetryPolicy, with_retries


def test_retry_policy_generates_backoff_sequence() -> None:
    policy = RetryPolicy(retries=4, base_delay=0.1, max_delay=1.0, jitter=False)
    assert list(policy.sleep_durations()) == [0.1, 0.2, 0.4]


def test_with_retries_eventually_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"count": 0}

    def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ValueError("not yet")
        return "ok"

    monkeypatch.setattr("time.sleep", lambda _: None)
    result = with_retries(flaky, (ValueError,), policy=RetryPolicy(retries=5, base_delay=0.01, jitter=False))
    assert result == "ok"
    assert attempts["count"] == 3


def test_with_retries_raises_after_exhaustion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _: None)

    def always_fail() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RetryExhaustedError):
        with_retries(always_fail, (RuntimeError,), policy=RetryPolicy(retries=2, base_delay=0.01, jitter=False))


def test_circuit_breaker_trips_and_resets(monkeypatch: pytest.MonkeyPatch) -> None:
    breaker = CircuitBreaker(fail_threshold=2, reset_timeout=0.01)
    attempts: list[int] = []

    def failing_call() -> None:
        attempts.append(1)
        raise RuntimeError("fail")

    monkeypatch.setattr("time.sleep", lambda _: None)

    with pytest.raises(RetryExhaustedError):
        with_retries(failing_call, (RuntimeError,), policy=RetryPolicy(retries=2, base_delay=0.01, jitter=False), breaker=breaker)

    # Breaker should now be open and refuse further calls until timeout elapses.
    with pytest.raises(RetryExhaustedError):
        breaker.call(lambda: None)

    assert breaker._opened_at is not None
    # After timeout, breaker allows calls again.
    target_time = breaker._opened_at + breaker.reset_timeout + 0.1
    monkeypatch.setattr("time.monotonic", lambda: target_time)
    assert breaker.call(lambda: "ok") == "ok"
