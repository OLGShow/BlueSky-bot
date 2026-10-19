#!/usr/bin/env python3
"""
RETRY-002: RetryPolicy on OpenRouter / Pollinations + CLIENT short-circuit.

Hermetic: fake failing callables; monkeypatch asyncio.sleep / backoff.
No network.

Run:
  python tests/test_retry_policy_retry002.py
  python -m unittest tests.test_retry_policy_retry002
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from resilience_service import (  # noqa: E402
    ErrorClass,
    RetryPolicy,
    classify_error,
)
from openrouter_adapter import OpenRouterAI  # noqa: E402
from pollinations_adapter import PollinationsAI  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class TestClassifyErrorClient(unittest.TestCase):
    def test_client_4xx_classified(self):
        self.assertEqual(classify_error(RuntimeError("HTTP 400: bad")), ErrorClass.CLIENT)
        self.assertEqual(classify_error(RuntimeError("HTTP 404 not found")), ErrorClass.CLIENT)

    def test_rate_limit_and_server(self):
        self.assertEqual(classify_error(RuntimeError("HTTP 429 Too Many Requests")), ErrorClass.RATE_LIMIT)
        self.assertEqual(classify_error(RuntimeError("rate limit exceeded")), ErrorClass.RATE_LIMIT)
        self.assertEqual(classify_error(RuntimeError("ratelimit")), ErrorClass.RATE_LIMIT)
        self.assertEqual(classify_error(RuntimeError("too many requests")), ErrorClass.RATE_LIMIT)
        self.assertEqual(classify_error(RuntimeError("HTTP 503 unavailable")), ErrorClass.SERVER)

    def test_generate_not_rate_limit(self):
        """Bare 'rate' must not match substrings like 'geneRATE'."""
        self.assertNotEqual(
            classify_error(RuntimeError("Failed to generate response")),
            ErrorClass.RATE_LIMIT,
        )
        self.assertEqual(
            classify_error(RuntimeError("Failed to generate response")),
            ErrorClass.UNKNOWN,
        )


class TestRetryPolicyExecute(unittest.TestCase):
    def setUp(self):
        self.sleep_patch = mock.patch(
            "resilience_service.asyncio.sleep",
            new_callable=mock.AsyncMock,
        )
        self.backoff_patch = mock.patch(
            "resilience_service.backoff_seconds",
            return_value=0.0,
        )
        self.mock_sleep = self.sleep_patch.start()
        self.backoff_patch.start()

    def tearDown(self):
        self.sleep_patch.stop()
        self.backoff_patch.stop()

    def test_success_after_retry(self):
        calls = {"n": 0}

        async def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("HTTP 503 temporary")
            return "ok"

        policy = RetryPolicy(max_retries=3, retry_budget=10)
        result = _run(policy.execute(flaky))
        self.assertEqual(result, "ok")
        self.assertEqual(calls["n"], 3)
        self.assertGreaterEqual(self.mock_sleep.await_count, 2)

    def test_exhaust_retries(self):
        calls = {"n": 0}

        async def always_fail():
            calls["n"] += 1
            raise RuntimeError("HTTP 502 bad gateway")

        policy = RetryPolicy(max_retries=3, retry_budget=10)
        with self.assertRaises(RuntimeError) as ctx:
            _run(policy.execute(always_fail))
        self.assertIn("502", str(ctx.exception))
        self.assertEqual(calls["n"], 3)

    def test_client_short_circuit_no_retry(self):
        calls = {"n": 0}

        async def client_err():
            calls["n"] += 1
            raise RuntimeError("HTTP 400: invalid request")

        policy = RetryPolicy(max_retries=5, retry_budget=10)
        with self.assertRaises(RuntimeError) as ctx:
            _run(policy.execute(client_err))
        self.assertIn("400", str(ctx.exception))
        self.assertEqual(calls["n"], 1)
        self.mock_sleep.assert_not_awaited()

    def test_budget_exhaust(self):
        calls = {"n": 0}

        async def fail():
            calls["n"] += 1
            raise RuntimeError("connection timed out")

        policy = RetryPolicy(max_retries=10, retry_budget=2)
        with self.assertRaises(RuntimeError):
            _run(policy.execute(fail))
        # First failure uses budget slot 1, second uses 2, third exceeds budget
        self.assertEqual(calls["n"], 3)

    def test_shared_policy_budget_resets_per_execute(self):
        """Lifetime-used budget must not starve later execute() calls on a shared policy."""
        policy = RetryPolicy(max_retries=3, retry_budget=2)

        async def always_fail():
            raise RuntimeError("HTTP 503 temporary")

        for _ in range(4):
            with self.assertRaises(RuntimeError):
                _run(policy.execute(always_fail))

        calls = {"n": 0}

        async def succeed_after_one():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("HTTP 503 temporary")
            return "ok"

        result = _run(policy.execute(succeed_after_one))
        self.assertEqual(result, "ok")
        self.assertEqual(calls["n"], 2)


class TestOpenRouterUsesRetryPolicy(unittest.TestCase):
    def setUp(self):
        self.sleep_patch = mock.patch(
            "resilience_service.asyncio.sleep",
            new_callable=mock.AsyncMock,
        )
        self.backoff_patch = mock.patch(
            "resilience_service.backoff_seconds",
            return_value=0.0,
        )
        self.sleep_patch.start()
        self.backoff_patch.start()
        os.environ["OPENROUTER_API_KEY"] = "test-key-retry002"

    def tearDown(self):
        self.sleep_patch.stop()
        self.backoff_patch.stop()
        os.environ.pop("OPENROUTER_API_KEY", None)

    def test_chat_retries_then_success(self):
        policy = RetryPolicy(max_retries=3, retry_budget=10)
        ai = OpenRouterAI(api_key="test-key-retry002", retry_policy=policy)
        calls = {"n": 0}

        async def once(_payload):
            calls["n"] += 1
            if calls["n"] < 2:
                raise RuntimeError("HTTP 503 upstream")
            return "hello"

        with mock.patch.object(ai, "_chat_completion_once", side_effect=once):
            result = _run(ai._chat_completion({"model": "x"}))
        self.assertEqual(result, "hello")
        self.assertEqual(calls["n"], 2)

    def test_chat_client_no_retry(self):
        policy = RetryPolicy(max_retries=4, retry_budget=10)
        ai = OpenRouterAI(api_key="test-key-retry002", retry_policy=policy)
        calls = {"n": 0}

        async def once(_payload):
            calls["n"] += 1
            raise RuntimeError("HTTP 422: unprocessable")

        with mock.patch.object(ai, "_chat_completion_once", side_effect=once):
            result = _run(ai._chat_completion({"model": "x"}))
        self.assertIsNone(result)
        self.assertEqual(calls["n"], 1)

    def test_set_retry_policy(self):
        ai = OpenRouterAI(api_key="test-key-retry002")
        custom = RetryPolicy(max_retries=1, retry_budget=1)
        ai.set_retry_policy(custom)
        self.assertIs(ai._retry_policy, custom)


class TestPollinationsUsesRetryPolicy(unittest.TestCase):
    def setUp(self):
        self.sleep_patch = mock.patch(
            "resilience_service.asyncio.sleep",
            new_callable=mock.AsyncMock,
        )
        self.backoff_patch = mock.patch(
            "resilience_service.backoff_seconds",
            return_value=0.0,
        )
        self.sleep_patch.start()
        self.backoff_patch.start()

    def tearDown(self):
        self.sleep_patch.stop()
        self.backoff_patch.stop()

    def test_make_request_retries_then_success(self):
        policy = RetryPolicy(max_retries=3, retry_budget=10)
        ai = PollinationsAI(retry_policy=policy)
        calls = {"n": 0}

        async def once(url, params, timeout=30):
            calls["n"] += 1
            if calls["n"] < 2:
                raise RuntimeError("HTTP 502 gateway")
            return "generated"

        with mock.patch.object(ai, "_make_request_once", side_effect=once):
            result = _run(ai._make_request("https://example.test/", {}))
        self.assertEqual(result, "generated")
        self.assertEqual(calls["n"], 2)

    def test_make_request_exhaust(self):
        policy = RetryPolicy(max_retries=2, retry_budget=10)
        ai = PollinationsAI(retry_policy=policy)
        calls = {"n": 0}

        async def once(url, params, timeout=30):
            calls["n"] += 1
            raise RuntimeError("HTTP 503")

        with mock.patch.object(ai, "_make_request_once", side_effect=once):
            result = _run(ai._make_request("https://example.test/", {}))
        self.assertIsNone(result)
        self.assertEqual(calls["n"], 2)

    def test_client_short_circuit(self):
        policy = RetryPolicy(max_retries=5, retry_budget=10)
        ai = PollinationsAI(retry_policy=policy)
        calls = {"n": 0}

        async def once(url, params, timeout=30):
            calls["n"] += 1
            raise RuntimeError("HTTP 404: Model not found")

        with mock.patch.object(ai, "_make_request_once", side_effect=once):
            result = _run(ai._make_request("https://example.test/", {}))
        self.assertIsNone(result)
        self.assertEqual(calls["n"], 1)


class TestNoAdHocRetryLoopsInAdapters(unittest.TestCase):
    """Adapters must not keep local for-attempt sleep retry loops."""

    def test_openrouter_has_no_attempt_loop(self):
        src = (APP_DIR / "openrouter_adapter.py").read_text(encoding="utf-8")
        self.assertNotIn("for attempt in range", src)
        self.assertIn("self._retry_policy.execute", src)

    def test_pollinations_has_no_attempt_loop(self):
        src = (APP_DIR / "pollinations_adapter.py").read_text(encoding="utf-8")
        self.assertNotIn("for attempt in range", src)
        self.assertIn("self._retry_policy.execute", src)


if __name__ == "__main__":
    unittest.main()
