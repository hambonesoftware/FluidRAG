"""Retry and circuit breaker utilities."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, Iterable, Optional, Tuple

from .errors import RetryExhaustedError


@dataclass
class RetryPolicy:
    """Configurable retry policy with backoff."""

    retries: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0
    jitter: bool = True

    def sleep_durations(self) -> Iterable[float]:
        """Yield backoff durations."""

        for attempt in range(self.retries):
            delay = min(self.max_delay, self.base_delay * (2**attempt))
            if self.jitter:
                delay *= random.uniform(0.5, 1.5)
            yield delay


@dataclass
class CircuitBreaker:
    """Simple circuit breaker."""

    fail_threshold: int = 5
    reset_timeout: float = 30.0
    _failures: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)
    _lock: Lock = field(default_factory=Lock, init=False)

    def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Protect call with breaker."""

        with self._lock:
            now = time.monotonic()
            if self._opened_at and now - self._opened_at < self.reset_timeout:
                raise RetryExhaustedError("Circuit breaker open")
            if self._opened_at and now - self._opened_at >= self.reset_timeout:
                self._failures = 0
                self._opened_at = None

        try:
            result = fn(*args, **kwargs)
        except Exception:
            with self._lock:
                self._failures += 1
                if self._failures >= self.fail_threshold:
                    self._opened_at = time.monotonic()
            raise
        else:
            with self._lock:
                self._failures = 0
                self._opened_at = None
            return result


def with_retries(
    fn: Callable[..., Any],
    exceptions: Tuple[type[Exception], ...],
    *,
    policy: RetryPolicy | None = None,
    breaker: CircuitBreaker | None = None,
    args: Tuple[Any, ...] | None = None,
    kwargs: dict[str, Any] | None = None,
) -> Any:
    """Execute with retries/backoff and optional circuit breaker."""

    args = args or ()
    kwargs = kwargs or {}
    policy = policy or RetryPolicy()

    def invoke() -> Any:
        return fn(*args, **kwargs)

    if breaker is not None:
        call_fn = lambda: breaker.call(invoke)  # noqa: E731 - simple wrapper
    else:
        call_fn = invoke

    last_error: Optional[Exception] = None
    for delay in (*policy.sleep_durations(), None):
        try:
            return call_fn()
        except exceptions as exc:  # type: ignore[arg-type]
            last_error = exc
            if delay is None:
                break
            time.sleep(delay)
        except Exception:
            raise
    raise RetryExhaustedError(str(last_error) if last_error else "Retries exhausted") from last_error
