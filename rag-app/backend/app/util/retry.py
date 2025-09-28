"""Retry and circuit breaker utilities."""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass
from typing import Any, Callable, Generator, Iterable, Optional, Type

from .errors import RetryExhaustedError


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    backoff_factor: float = 0.5
    max_backoff: float = 4.0

    def sleep_durations(self) -> Iterable[float]:
        for attempt in range(self.attempts):
            delay = min(self.backoff_factor * (2 ** attempt), self.max_backoff)
            yield delay


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, reset_timeout: float = 60.0) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.opened_at: Optional[float] = None

    def _trip_if_needed(self) -> None:
        if self.failure_count >= self.failure_threshold:
            self.opened_at = time.monotonic()

    def _can_attempt(self) -> bool:
        if self.opened_at is None:
            return True
        if time.monotonic() - self.opened_at >= self.reset_timeout:
            self.failure_count = 0
            self.opened_at = None
            return True
        return False

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        if not self._can_attempt():
            raise RetryExhaustedError("Circuit breaker open")
        try:
            result = func(*args, **kwargs)
        except Exception:
            self.failure_count += 1
            self._trip_if_needed()
            raise
        self.failure_count = 0
        self.opened_at = None
        return result


def with_retries(
    func: Callable[..., Any],
    *,
    policy: RetryPolicy | None = None,
    retriable: tuple[Type[BaseException], ...] = (Exception,),
) -> Callable[..., Any]:
    policy = policy or RetryPolicy()

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        last_exc: Optional[BaseException] = None
        for delay in itertools.chain(policy.sleep_durations(), [None]):
            try:
                return func(*args, **kwargs)
            except retriable as exc:
                last_exc = exc
                if delay is None:
                    break
                time.sleep(delay)
        raise RetryExhaustedError("Retry attempts exhausted") from last_exc

    return wrapper
