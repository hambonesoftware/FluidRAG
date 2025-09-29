"""Retry and circuit breaker utilities."""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from .errors import RetryExhaustedError


@dataclass
class RetryPolicy:
    """Configurable retry policy with backoff."""

    retries: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0
    jitter: bool = True
    _rng: random.Random = field(default_factory=random.Random, repr=False)

    def __init__(
        self,
        retries: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 8.0,
        jitter: bool = True,
    ) -> None:
        """Initialize policy"""
        self.retries = retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self._rng = random.Random()
        self.__post_init__()

    def __post_init__(self) -> None:
        if self.retries < 1:
            raise ValueError("retries must be >= 1")
        if self.base_delay <= 0:
            raise ValueError("base_delay must be > 0")
        if self.max_delay < self.base_delay:
            raise ValueError("max_delay must be >= base_delay")

    def sleep_durations(self) -> Iterator[float]:
        """Yield backoff durations."""
        delay = self.base_delay
        for _ in range(self.retries - 1):
            jittered = delay
            if self.jitter:
                jittered = self._rng.uniform(delay * 0.5, delay * 1.5)
            yield min(jittered, self.max_delay)
            delay = min(delay * 2, self.max_delay)


class CircuitBreaker:
    """Simple circuit breaker."""

    def __init__(self, fail_threshold: int = 5, reset_timeout: float = 30.0) -> None:
        """Init."""
        if fail_threshold < 1:
            raise ValueError("fail_threshold must be >= 1")
        if reset_timeout <= 0:
            raise ValueError("reset_timeout must be > 0")
        self.fail_threshold = fail_threshold
        self.reset_timeout = reset_timeout
        self._failures = 0
        self._state = "closed"
        self._opened_at: float | None = None

    def _trip(self) -> None:
        self._state = "open"
        self._opened_at = time.monotonic()

    def _reset(self) -> None:
        self._state = "closed"
        self._failures = 0
        self._opened_at = None

    def _can_attempt(self) -> bool:
        if self._state != "open":
            return True
        assert self._opened_at is not None
        if time.monotonic() - self._opened_at >= self.reset_timeout:
            self._state = "half-open"
            return True
        return False

    def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Protect call with breaker."""
        if not self._can_attempt():
            raise RetryExhaustedError("circuit breaker open")
        try:
            result = fn(*args, **kwargs)
        except Exception:
            self._failures += 1
            if self._failures >= self.fail_threshold:
                self._trip()
            raise
        else:
            self._reset()
            return result


def with_retries(
    fn: Callable[..., Any],
    exceptions: tuple[type[BaseException], ...],
    policy: RetryPolicy | None = None,
    breaker: CircuitBreaker | None = None,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Execute with retries/backoff and optional circuit breaker"""
    if policy is None:
        policy = RetryPolicy()
    attempts = 0
    delays = iter(policy.sleep_durations())
    last_exc: BaseException | None = None

    while True:
        attempts += 1
        try:
            if breaker is not None:
                return breaker.call(fn, *args, **kwargs)
            return fn(*args, **kwargs)
        except exceptions as exc:
            last_exc = exc
            try:
                delay = next(delays)
            except StopIteration:
                break
            time.sleep(delay)
        except RetryExhaustedError:
            raise

    raise RetryExhaustedError(
        f"Retries exhausted after {attempts} attempts"
    ) from last_exc


__all__ = ["RetryPolicy", "CircuitBreaker", "with_retries"]
