#!/usr/bin/env python3
"""FOL-001: follow_strategy hermetic tests."""

from __future__ import annotations

import ast
import asyncio
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import List

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
        from follow_strategy import REASON_QUALITY_OK, should_follow_user

        actor = types.SimpleNamespace(
            description="Python developer and writer",
            followers_count=100,
            follows_count=50,
            posts_count=20,
        )
        ok, reason = should_follow_user(actor)
        self.assertTrue(ok)
        self.assertEqual(reason, REASON_QUALITY_OK)

    def test_quality_ok_without_keyword_when_not_required(self) -> None:
        from follow_strategy import (
            REASON_QUALITY_OK,
            REASON_REJECTED,
            should_follow_user,
        )

        actor = types.SimpleNamespace(
            description="just a person who likes coffee",
            followers_count=100,
            follows_count=50,
            posts_count=20,
        )
        ok, reason = should_follow_user(actor, require_bio_keyword=False)
        self.assertTrue(ok)
        self.assertEqual(reason, REASON_QUALITY_OK)
        ok2, reason2 = should_follow_user(actor, require_bio_keyword=True)
        self.assertFalse(ok2)
        self.assertEqual(reason2, REASON_REJECTED)

    def test_liked_enough_bypasses_keyword(self) -> None:
        from follow_strategy import REASON_LIKED_ENOUGH, should_follow_user

        actor = types.SimpleNamespace(
            description="coffee only",
            followers_count=100,
            follows_count=50,
            posts_count=20,
        )
        ok, reason = should_follow_user(
            actor,
            require_bio_keyword=True,
            liked_count=2,
            min_likes_for_follow=2,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, REASON_LIKED_ENOUGH)

    def test_keyword_reason_when_required(self) -> None:
        from follow_strategy import REASON_KEYWORD, should_follow_user

        actor = types.SimpleNamespace(
            description="Python developer",
            followers_count=100,
            follows_count=50,
            posts_count=20,
        )
        ok, reason = should_follow_user(
            actor,
            require_bio_keyword=True,
            liked_count=0,
        )
        self.assertTrue(ok)
        self.assertEqual(reason, REASON_KEYWORD)

    def test_rejects_mega_influencer(self) -> None:
        from follow_strategy import REASON_REJECTED, should_follow_user

        actor = types.SimpleNamespace(
            description="artist",
            followers_count=200000,
            follows_count=10,
            posts_count=100,
        )
        ok, reason = should_follow_user(actor)
        self.assertFalse(ok)
        self.assertEqual(reason, REASON_REJECTED)


class TestFollowOrchestrator(unittest.TestCase):
    def test_suggestions_respects_max_follows(self) -> None:
        from follow_strategy import (
            CallableFollowPorts,
            FollowPolicy,
            FollowStrategyOrchestrator,
        )

        followed: List[str] = []

        async def get_suggestions(*, limit: int = 30):
            actors = [
                types.SimpleNamespace(did=f"did:{i}", handle=f"u{i}") for i in range(5)
            ]
            return types.SimpleNamespace(actors=actors)

        async def get_profile(did: str):
            return types.SimpleNamespace(
                did=did,
                handle=did.replace("did:", "u"),
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
        policy = FollowPolicy(max_follows_per_pass=3, require_bio_keyword=False)
        n = asyncio.run(
            FollowStrategyOrchestrator(ports, policy=policy).from_suggestions()
        )
        self.assertEqual(n, 3)
        self.assertEqual(len(followed), 3)

    def test_run_fills_from_timeline_after_suggestions(self) -> None:
        from follow_strategy import (
            CallableFollowPorts,
            FollowPolicy,
            FollowStrategyOrchestrator,
        )

        followed: List[str] = []

        async def get_suggestions(*, limit: int = 30):
            return types.SimpleNamespace(actors=[])

        async def get_profile(did: str):
            return types.SimpleNamespace(
                did=did,
                handle="author1",
                description="tech notes",
                followers_count=500,
                follows_count=100,
                posts_count=40,
            )

        async def get_timeline(*, limit: int = 30):
            author = types.SimpleNamespace(did="did:tl1", handle="author1")
            post = types.SimpleNamespace(
                author=author, like_count=40, repost_count=5
            )
            return types.SimpleNamespace(
                feed=[types.SimpleNamespace(post=post)]
            )

        async def follow(*, did: str, handle: str, source: str) -> bool:
            followed.append(f"{source}:{did}")
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
        policy = FollowPolicy(
            max_follows_per_pass=2,
            require_bio_keyword=False,
            timeline_min_engagement=30,
        )
        asyncio.run(FollowStrategyOrchestrator(ports, policy=policy).run())
        self.assertEqual(followed, ["timeline:did:tl1"])

    def test_policy_from_config(self) -> None:
        from follow_strategy import FollowPolicy

        p = FollowPolicy.from_bot_config(
            {
                "follow_strategy": {
                    "every_n_cycles": 2,
                    "max_follows_per_pass": 3,
                    "require_bio_keyword": False,
                }
            }
        )
        self.assertEqual(p.every_n_cycles, 2)
        self.assertEqual(p.max_follows_per_pass, 3)
        self.assertFalse(p.require_bio_keyword)

    def test_logs_follow_quality_on_success(self) -> None:
        from agent_decision_log import AgentDecisionLog
        from follow_strategy import (
            CallableFollowPorts,
            FollowPolicy,
            FollowStrategyOrchestrator,
            REASON_QUALITY_OK,
        )

        with tempfile.TemporaryDirectory() as tmp:
            log_path = str(Path(tmp) / "decisions.jsonl")
            decision_log = AgentDecisionLog(path=log_path, max_lines=100)

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
            policy = FollowPolicy(max_follows_per_pass=1, require_bio_keyword=False)
            n = asyncio.run(
                FollowStrategyOrchestrator(
                    ports, policy=policy, decision_log=decision_log
                ).from_suggestions()
            )
            self.assertEqual(n, 1)
            entries = decision_log.recent(5)
            self.assertEqual(len(entries), 1)
            entry = entries[0]
            self.assertEqual(entry["domain"], "follow")
            self.assertEqual(entry["action"], "follow")
            self.assertEqual(entry["arm"], "suggestions")
            self.assertEqual(entry["reason"], REASON_QUALITY_OK)
            self.assertEqual(entry["context"]["did"], "did:1")
            self.assertEqual(entry["context"]["handle"], "u1")


if __name__ == "__main__":
    unittest.main()
