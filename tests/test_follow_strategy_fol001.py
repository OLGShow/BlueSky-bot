#!/usr/bin/env python3
"""FOL-001: follow_strategy hermetic tests."""

from __future__ import annotations

import ast
import asyncio
import sys
import types
import unittest
from pathlib import Path
from typing import Any, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


class TestShouldFollow(unittest.TestCase):
    def test_acyclic(self) -> None:
        path = APP_DIR / "follow_strategy.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn("bluesky_bot_v2", node.module or "")

    def test_keyword_match(self) -> None:
        from follow_strategy import should_follow_user

        actor = types.SimpleNamespace(
            description="Python developer and writer",
            followers_count=100,
            follows_count=50,
            posts_count=20,
        )
        self.assertTrue(should_follow_user(actor))

    def test_rejects_mega_influencer(self) -> None:
        from follow_strategy import should_follow_user

        actor = types.SimpleNamespace(
            description="artist",
            followers_count=200000,
            follows_count=10,
            posts_count=100,
        )
        self.assertFalse(should_follow_user(actor))


class TestFollowOrchestrator(unittest.TestCase):
    def test_suggestions_follow_once(self) -> None:
        from follow_strategy import CallableFollowPorts, FollowStrategyOrchestrator

        followed: List[str] = []

        async def get_suggestions(*, limit: int = 30):
            return types.SimpleNamespace(
                actors=[types.SimpleNamespace(did="did:1", handle="u1")]
            )

        async def get_profile(did: str):
            return types.SimpleNamespace(
                did=did,
                handle="u1",
                description="developer python",
                followers_count=100,
                follows_count=40,
                posts_count=20,
            )

        async def get_timeline(*, limit: int = 30):
            return types.SimpleNamespace(feed=[])

        async def follow(*, did: str, handle: str, source: str) -> bool:
            followed.append(did)
            return True

        async def no_sleep(_s: float) -> None:
            return None

        ports = CallableFollowPorts(
            _get_suggestions=get_suggestions,
            _get_profile=get_profile,
            _get_timeline=get_timeline,
            _follow=follow,
            _update_relationship=lambda *a: None,
            _get_my_did=lambda: "did:me",
            _followed_users=set(),
            sleep=no_sleep,
        )
        n = asyncio.run(FollowStrategyOrchestrator(ports).from_suggestions())
        self.assertEqual(n, 1)
        self.assertEqual(followed, ["did:1"])


if __name__ == "__main__":
    unittest.main()
