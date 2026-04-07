#!/usr/bin/env python3
"""
ResilienceService — unified retry policy, per-subsystem circuit breakers,
exponential backoff with jitter, and retry budgets.
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class ErrorClass(Enum):
    RATE_LIMIT = 'rate_limit'     # 429
    SERVER = 'server'             # 5xx
    NETWORK = 'network'           # timeout / connection
    AUTH = 'auth'                 # 401 / 403
    CLIENT = 'client'             # 4xx (non-429)
    UNKNOWN = 'unknown'


def classify_error(error: Exception) -> ErrorClass:
    msg = str(error).lower()
    if '429' in msg or 'rate' in msg or 'ratelimit' in msg:
        return ErrorClass.RATE_LIMIT
    if any(c in msg for c in ('401', '403', 'unauthorized', 'forbidden')):
        return ErrorClass.AUTH
    if any(c in msg for c in ('500', '502', '503', '504')):
        return ErrorClass.SERVER
    if any(c in msg for c in ('timeout', 'timed out', 'connectionerror', 'connect', 'dns')):
        return ErrorClass.NETWORK
    if any(c in msg for c in ('400', '404', '405', '422')):
        return ErrorClass.CLIENT
    return ErrorClass.UNKNOWN


_BACKOFF_PROFILES = {
    ErrorClass.RATE_LIMIT: {'base': 120, 'max': 900, 'factor': 2.0},
    ErrorClass.SERVER:     {'base': 30,  'max': 600, 'factor': 2.0},
    ErrorClass.NETWORK:    {'base': 10,  'max': 300, 'factor': 2.0},
    ErrorClass.AUTH:       {'base': 60,  'max': 300, 'factor': 1.5},
    ErrorClass.CLIENT:     {'base': 5,   'max': 30,  'factor': 1.5},
    ErrorClass.UNKNOWN:    {'base': 30,  'max': 300, 'factor': 2.0},
}


def backoff_seconds(error_class: ErrorClass, attempt: int) -> float:
    profile = _BACKOFF_PROFILES[error_class]
    delay = profile['base'] * (profile['factor'] ** (attempt - 1))
    delay = min(delay, profile['max'])
    jitter = random.uniform(0, delay * 0.25)
    return delay + jitter


@dataclass
class CircuitBreaker:
    """Per-subsystem circuit breaker (closed -> open -> half-open -> closed).

    - After ``failure_threshold`` consecutive failures the breaker opens.
    - After ``recovery_timeout`` seconds it moves to half-open (one probe allowed).
    - A single success in half-open closes the breaker; a failure reopens it.
    """

    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 300.0  # seconds
    _failures: int = field(default=0, init=False, repr=False)
    _state: str = field(default='closed', init=False)
    _opened_at: float = field(default=0.0, init=False, repr=False)

    @property
    def state(self) -> str:
        if self._state == 'open':
            if time.time() - self._opened_at >= self.recovery_timeout:
                self._state = 'half_open'
        return self._state

    def record_success(self) -> None:
        self._failures = 0
        if self._state in ('half_open', 'open'):
            logger.info(f"CircuitBreaker[{self.name}] closed (recovered)")
        self._state = 'closed'

    def record_failure(self) -> None:
        self._failures += 1
        if self._state == 'half_open':
            self._state = 'open'
            self._opened_at = time.time()
            logger.warning(f"CircuitBreaker[{self.name}] reopened after half-open probe failure")
        elif self._failures >= self.failure_threshold and self._state == 'closed':
            self._state = 'open'
            self._opened_at = time.time()
            logger.warning(f"CircuitBreaker[{self.name}] opened after {self._failures} failures")

    def allow_request(self) -> bool:
        s = self.state
        if s == 'closed':
            return True
        if s == 'half_open':
            return True
        return False


class RetryPolicy:
    """Wraps async callables with retry + backoff + circuit-breaker awareness.

    Usage::

        policy = RetryPolicy(breaker=my_breaker, max_retries=3)
        result = await policy.execute(some_async_func, arg1, arg2)
    """

    def __init__(self, breaker: Optional[CircuitBreaker] = None,
                 max_retries: int = 3, retry_budget: int = 10):
        self.breaker = breaker
        self.max_retries = max_retries
        self.retry_budget = retry_budget
        self._budget_used = 0

    async def execute(self, fn: Callable, *args, **kwargs):
        if self.breaker and not self.breaker.allow_request():
            raise RuntimeError(f"CircuitBreaker[{self.breaker.name}] is open — request blocked")

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result = await fn(*args, **kwargs)
                if self.breaker:
                    self.breaker.record_success()
                return result
            except Exception as e:
                last_error = e
                ec = classify_error(e)
                if ec == ErrorClass.CLIENT:
                    if self.breaker:
                        self.breaker.record_failure()
                    raise

                self._budget_used += 1
                if self._budget_used > self.retry_budget:
                    logger.warning(f"Retry budget exhausted ({self.retry_budget})")
                    if self.breaker:
                        self.breaker.record_failure()
                    raise

                if attempt < self.max_retries:
                    delay = backoff_seconds(ec, attempt)
                    logger.warning(
                        f"Retry {attempt}/{self.max_retries} for {fn.__name__} "
                        f"({ec.value}, backoff {delay:.1f}s): {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    if self.breaker:
                        self.breaker.record_failure()

        raise last_error  # type: ignore[misc]

    def reset_budget(self) -> None:
        self._budget_used = 0
