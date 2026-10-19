#!/usr/bin/env python3
"""ENG-001: SmartEngagementOrchestrator hermetic tests."""

from __future__ import annotations

import ast
import asyncio
import sys
import types
import unittest
from pathlib import Path
from typing import Any, List, Optional
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def _feed_item(uri: str, text: str, did: str = "did:other", handle: str = "u"):
    record = types.SimpleNamespace(text=text, created_at="2026-10-19T12:00:00Z")
    author = types.SimpleNamespace(did=did, handle=handle)
    post = types.SimpleNamespace(uri=uri, cid="cid1", author=author, record=record)
    return types.SimpleNamespace(post=post)


class FakeTimeline:
    def __init__(self, items: List[Any]) -> None:
        self.items = items
        self.calls = 0

    async def fetch(self, *, limit: int, cursor: Optional[str] = None):
        self.calls += 1
        return types.SimpleNamespace(feed=self.items, cursor=None)


class TestSmartEngagement(unittest.TestCase):
    def test_acyclic(self) -> None:
        path = APP_DIR / "smart_engagement.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn("bluesky_bot_v2", node.module or "")

    def test_likes_above_threshold(self) -> None:
        from smart_engagement import (
            CallableRelevance,
            CallableRepostPolicy,
            SmartEngagementConfig,
            SmartEngagementOrchestrator,
            SmartEngagementPorts,
        )

        liked: List[str] = []
        snippets: List[str] = []

        async def like(**kwargs) -> bool:
            liked.append(kwargs["uri"])
            return True

        async def repost(**kwargs) -> bool:
            return False

        async def no_sleep(_s: float) -> None:
            return None

        ports = SmartEngagementPorts(
            timeline=FakeTimeline(
                [_feed_item("at://p1", "interesting AI tooling post")]
            ),
            relevance=CallableRelevance(lambda text, post: 0.5),
            like=like,
            repost=repost,
            repost_policy=CallableRepostPolicy(lambda *a: (False, "skip")),
            update_relationship=lambda *a: None,
            get_my_did=lambda: "did:me",
            reposted_uris=set(),
            recent_repost_authors=[],
            set_trend_snippets=lambda s: snippets.extend(s),
            get_session_likes=lambda: 1,
            bump_errors=lambda: None,
            sleep=no_sleep,
        )
        orch = SmartEngagementOrchestrator(ports)
        cfg = SmartEngagementConfig(
            like_threshold=0.2,
            max_reposts=0,
            max_interactions=5,
            repost_probability=0.0,
            timeline_pages=1,
        )
        with patch("smart_engagement.random.random", return_value=0.99):
            asyncio.run(orch.run(cfg))

        self.assertEqual(liked, ["at://p1"])
        self.assertTrue(snippets)

    def test_skips_own_posts(self) -> None:
        from smart_engagement import (
            CallableRelevance,
            CallableRepostPolicy,
            SmartEngagementConfig,
            SmartEngagementOrchestrator,
            SmartEngagementPorts,
        )

        liked: List[str] = []

        async def like(**kwargs) -> bool:
            liked.append(kwargs["uri"])
            return True

        async def no_sleep(_s: float) -> None:
            return None

        ports = SmartEngagementPorts(
            timeline=FakeTimeline(
                [_feed_item("at://mine", "hello", did="did:me")]
            ),
            relevance=CallableRelevance(lambda text, post: 0.9),
            like=like,
            repost=like,
            repost_policy=CallableRepostPolicy(lambda *a: (True, "")),
            update_relationship=lambda *a: None,
            get_my_did=lambda: "did:me",
            reposted_uris=set(),
            recent_repost_authors=[],
            set_trend_snippets=lambda s: None,
            get_session_likes=lambda: 0,
            bump_errors=lambda: None,
            sleep=no_sleep,
        )
        asyncio.run(
            SmartEngagementOrchestrator(ports).run(
                SmartEngagementConfig(like_threshold=0.1, max_reposts=0)
            )
        )
        self.assertEqual(liked, [])


if __name__ == "__main__":
    unittest.main()
