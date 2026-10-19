#!/usr/bin/env python3
"""
RETRY-003: RetryPolicy on ATProto + media upload + engagement writes.

Hermetic: fake failing callables; monkeypatch asyncio.sleep / backoff.
No network.

Run:
  python tests/test_retry_policy_retry003.py
  python -m unittest tests.test_retry_policy_retry003
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from typing import Any, List, Optional, Set
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from resilience_service import (  # noqa: E402
    RetryPolicy,
    build_outbound_retry_policies,
)
from engagement_ports import (  # noqa: E402
    DryRunGate,
    EngagementConfigView,
    EngagementIdentityView,
    EngagementPorts,
    UnlimitedBudget,
)
from engagement_service import EngagementService  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class FakeLedger:
    def __init__(self):
        self._keys: Set[str] = set()
        self.recorded: List[str] = []

    def contains(self, key: str) -> bool:
        return key in self._keys

    def record(self, key: str) -> None:
        self._keys.add(key)
        self.recorded.append(key)


class FakeClient:
    def __init__(self):
        self.like_calls = 0
        self.repost_calls = 0
        self.follow_calls = 0
        self._like_fail_until = 0
        self._like_error: Optional[Exception] = None

    def fail_like_until(self, n: int, error: Exception) -> None:
        self._like_fail_until = n
        self._like_error = error

    async def like(self, uri: str, cid: str) -> Any:
        self.like_calls += 1
        if self.like_calls <= self._like_fail_until and self._like_error is not None:
            raise self._like_error
        return None

    async def repost(self, uri: str, cid: str) -> Any:
        self.repost_calls += 1
        return None

    async def follow(self, did: str) -> Any:
        self.follow_calls += 1
        return None


def _engagement_ports(client: FakeClient, retry: Optional[RetryPolicy] = None) -> EngagementPorts:
    return EngagementPorts(
        client=client,
        ledger=FakeLedger(),
        budget=UnlimitedBudget(),
        dry_run=DryRunGate(enabled=False, _logger=None),
        stats={"likes_given": 0, "reposts_made": 0, "follows_made": 0},
        identity=EngagementIdentityView(
            liked_posts=set(),
            reposted_posts=set(),
            followed_users=set(),
            recent_repost_authors=[],
        ),
        config=EngagementConfigView(mode="open", whitelist=frozenset()),
        retry=retry,
    )


class TestOutboundPoliciesBounded(unittest.TestCase):
    def test_atproto_and_media_policies_bounded(self):
        policies = build_outbound_retry_policies()
        self.assertGreaterEqual(policies.atproto.max_retries, 1)
        self.assertGreaterEqual(policies.atproto.retry_budget, 1)
        self.assertGreaterEqual(policies.media_upload.max_retries, 1)
        self.assertGreaterEqual(policies.media_upload.retry_budget, 1)

    def test_rejects_infinite_max_retries(self):
        with self.assertRaises(ValueError):
            build_outbound_retry_policies(max_retries_atproto=0)


class TestEngagementAtprotoRetry(unittest.TestCase):
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

    def test_like_retries_then_success(self):
        policy = RetryPolicy(max_retries=3, retry_budget=10)
        client = FakeClient()
        client.fail_like_until(1, RuntimeError("HTTP 503 temporary"))
        svc = EngagementService(_engagement_ports(client, retry=policy))

        ok = _run(svc.like("at://post/1", "cid1", score=0.9))
        self.assertTrue(ok)
        self.assertEqual(client.like_calls, 2)
        self.assertGreaterEqual(self.mock_sleep.await_count, 1)

    def test_like_client_no_retry(self):
        policy = RetryPolicy(max_retries=5, retry_budget=10)
        client = FakeClient()
        client.fail_like_until(10, RuntimeError("HTTP 400: bad request"))
        svc = EngagementService(_engagement_ports(client, retry=policy))

        with self.assertRaises(RuntimeError) as ctx:
            _run(svc.like("at://post/2", "cid2", score=0.5))
        self.assertIn("400", str(ctx.exception))
        self.assertEqual(client.like_calls, 1)
        self.mock_sleep.assert_not_awaited()

    def test_like_without_retry_policy_calls_once(self):
        client = FakeClient()
        svc = EngagementService(_engagement_ports(client, retry=None))
        ok = _run(svc.like("at://post/3", "cid3", score=0.4))
        self.assertTrue(ok)
        self.assertEqual(client.like_calls, 1)


class TestMediaUploadRetryPolicy(unittest.TestCase):
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

    def test_upload_blob_retries_then_success(self):
        policy = RetryPolicy(max_retries=3, retry_budget=10)
        calls = {"n": 0}

        class _Blob:
            blob = {"ok": True}

        async def upload_blob(data: bytes):
            calls["n"] += 1
            if calls["n"] < 2:
                raise RuntimeError("HTTP 502 bad gateway")
            return _Blob()

        result = _run(policy.execute(upload_blob, b"img"))
        self.assertEqual(result.blob, {"ok": True})
        self.assertEqual(calls["n"], 2)

    def test_upload_blob_client_no_retry(self):
        policy = RetryPolicy(max_retries=4, retry_budget=10)
        calls = {"n": 0}

        async def upload_blob(data: bytes):
            calls["n"] += 1
            raise RuntimeError("HTTP 400: invalid blob")

        with self.assertRaises(RuntimeError):
            _run(policy.execute(upload_blob, b"img"))
        self.assertEqual(calls["n"], 1)
        self.mock_sleep.assert_not_awaited()


class TestBotSourceWiresRetry003(unittest.TestCase):
    """Primary ATProto / media paths must use RetryPolicy helpers (no ad-hoc login loop)."""

    def test_bot_uses_atproto_and_media_helpers(self):
        src = (APP_DIR / "bluesky_bot_v2.py").read_text(encoding="utf-8")
        self.assertIn("async def _atproto_execute", src)
        self.assertIn("async def _media_upload_execute", src)
        self.assertIn("self.retry_atproto.execute", src)
        self.assertIn("self.retry_media_upload.execute", src)
        self.assertIn("self._atproto_execute(", src)
        self.assertIn("self._media_upload_execute(", src)
        # Ad-hoc login rate-limit loop removed (RETRY-003)
        self.assertNotIn("base_delay = 60", src)
        self.assertNotIn("for attempt in range(max_retries):", src)

    def test_engagement_service_uses_retry_execute(self):
        src = (APP_DIR / "engagement_service.py").read_text(encoding="utf-8")
        self.assertIn("retry.execute", src)
        self.assertIn("_atproto_write", src)


if __name__ == "__main__":
    unittest.main()
