#!/usr/bin/env python3
"""PLRN-011: EngagementLearner hermetic tests."""

from __future__ import annotations

import ast
import asyncio
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional
REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


TOPIC_GROUPS = {
    "ai": {
        "keywords": ["ai", "llm", "gpt", "machine learning"],
        "weight": 0.12,
    },
    "tech": {
        "keywords": ["python", "programming", "api"],
        "weight": 0.10,
    },
}


def _feed_item(uri: str, text: str, did: str = "did:other", handle: str = "u"):
    record = types.SimpleNamespace(text=text, created_at="2026-10-19T12:00:00Z")
    author = types.SimpleNamespace(did=did, handle=handle)
    post = types.SimpleNamespace(uri=uri, cid="cid1", author=author, record=record)
    return types.SimpleNamespace(post=post)


class FakeTimeline:
    def __init__(self, items: List[Any]) -> None:
        self.items = items

    async def fetch(self, *, limit: int, cursor: Optional[str] = None):
        return types.SimpleNamespace(feed=self.items, cursor=None)


class TestEngagementLearnerCore(unittest.TestCase):
    def test_acyclic_no_bot_import(self) -> None:
        path = APP_DIR / "engagement_learner.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn("bluesky_bot_v2", node.module or "")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn("bluesky_bot_v2", alias.name)

    def test_infer_topic_and_other(self) -> None:
        from engagement_learner import OTHER_ARM, infer_topic

        self.assertEqual(infer_topic("New LLM and GPT tools", TOPIC_GROUPS), "ai")
        self.assertEqual(infer_topic("python api tutorial", TOPIC_GROUPS), "tech")
        self.assertEqual(infer_topic("cooking pasta tonight", TOPIC_GROUPS), OTHER_ARM)

    def test_multiplier_range(self) -> None:
        from engagement_learner import (
            EngagementLearner,
            topic_multiplier_from_mean,
        )
        from policy_learner import PolicyLearner

        self.assertAlmostEqual(topic_multiplier_from_mean(0.0), 0.5)
        self.assertAlmostEqual(topic_multiplier_from_mean(1.0), 1.5)
        self.assertAlmostEqual(topic_multiplier_from_mean(0.5), 1.0)

        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "learning_state_engagement.json")
            pl = PolicyLearner(
                path=path,
                params={},
                arm_keys=["ai", "tech", "_other"],
                bootstrap_weights={"ai": 0.33, "tech": 0.33, "_other": 0.34},
            )
            eng = EngagementLearner(pl, TOPIC_GROUPS, enabled=True)
            mult = eng.topic_multiplier("ai")
            self.assertGreaterEqual(mult, 0.5)
            self.assertLessEqual(mult, 1.5)

            eng_off = EngagementLearner(pl, TOPIC_GROUPS, enabled=False)
            self.assertEqual(eng_off.topic_multiplier("ai"), 1.0)

    def test_credit_updates_arms(self) -> None:
        from engagement_learner import EngagementLearner
        from policy_learner import PolicyLearner

        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "eng.json")
            pl = PolicyLearner(
                path=path,
                params={"min_settled_posts": 0},
                arm_keys=["ai", "_other"],
                bootstrap_weights={"ai": 0.5, "_other": 0.5},
            )
            eng = EngagementLearner(pl, {"ai": TOPIC_GROUPS["ai"]}, enabled=True)
            before = float(pl.arms["ai"]["alpha"])
            ok = eng.credit("ai", likes=10, replies=2, reposts=1, check_id="6h")
            self.assertTrue(ok)
            self.assertGreater(float(pl.arms["ai"]["alpha"]), before)
            self.assertGreater(pl.total_credit_mass, 0)

    def test_record_action_trims(self) -> None:
        from engagement_learner import (
            MAX_ENGAGEMENT_ACTIONS,
            EngagementLearner,
            append_engagement_action,
            build_like_action,
        )
        from policy_learner import PolicyLearner

        with tempfile.TemporaryDirectory() as tmp:
            pl = PolicyLearner(
                path=str(Path(tmp) / "e.json"),
                params={},
                arm_keys=["_other"],
                bootstrap_weights={"_other": 1.0},
            )
            eng = EngagementLearner(pl, {}, enabled=True)
            actions: list = []
            for i in range(MAX_ENGAGEMENT_ACTIONS + 20):
                eng.record_action(
                    actions,
                    kind="like",
                    topic="_other",
                    uri=f"at://post/{i}",
                )
            self.assertEqual(len(actions), MAX_ENGAGEMENT_ACTIONS)
            self.assertEqual(actions[-1]["uri"], f"at://post/{MAX_ENGAGEMENT_ACTIONS + 19}")

            # helper shape
            act = build_like_action(topic="ai", uri="at://x")
            self.assertEqual(act["rewarded_checks"], [])
            self.assertEqual(act["kind"], "like")
            append_engagement_action(actions, act, max_n=MAX_ENGAGEMENT_ACTIONS)
            self.assertEqual(len(actions), MAX_ENGAGEMENT_ACTIONS)


class TestEffectiveScoreGate(unittest.TestCase):
    def test_multiplier_gates_like(self) -> None:
        from smart_engagement import (
            CallableRelevance,
            CallableRepostPolicy,
            SmartEngagementConfig,
            SmartEngagementOrchestrator,
            SmartEngagementPorts,
        )

        liked: List[str] = []
        recorded: List[dict] = []

        async def like(**kwargs) -> bool:
            liked.append(kwargs["uri"])
            return True

        async def no_sleep(_s: float) -> None:
            return None

        # raw score 0.25; threshold 0.30 → without mult skip;
        # with mult 1.5 → effective 0.375 → like
        ports = SmartEngagementPorts(
            timeline=FakeTimeline(
                [_feed_item("at://p1", "great llm ai news")]
            ),
            relevance=CallableRelevance(lambda text, post: 0.25),
            like=like,
            repost=like,
            repost_policy=CallableRepostPolicy(lambda *a: (False, "skip")),
            update_relationship=lambda *a: None,
            get_my_did=lambda: "did:me",
            reposted_uris=set(),
            recent_repost_authors=[],
            set_trend_snippets=lambda s: None,
            get_session_likes=lambda: 0,
            bump_errors=lambda: None,
            sleep=no_sleep,
            infer_topic=lambda text: "ai",
            topic_multiplier=lambda topic: 1.5,
            on_like_action=lambda **kw: recorded.append(kw),
        )
        cfg = SmartEngagementConfig(
            like_threshold=0.30,
            max_reposts=0,
            max_interactions=5,
            timeline_pages=1,
        )
        asyncio.run(SmartEngagementOrchestrator(ports).run(cfg))
        self.assertEqual(liked, ["at://p1"])
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]["topic"], "ai")
        self.assertEqual(recorded[0]["uri"], "at://p1")

    def test_low_multiplier_blocks_like(self) -> None:
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

        # raw 0.35; mult 0.5 → effective 0.175 < 0.30
        ports = SmartEngagementPorts(
            timeline=FakeTimeline([_feed_item("at://p2", "text")]),
            relevance=CallableRelevance(lambda text, post: 0.35),
            like=like,
            repost=like,
            repost_policy=CallableRepostPolicy(lambda *a: (False, "skip")),
            update_relationship=lambda *a: None,
            get_my_did=lambda: "did:me",
            reposted_uris=set(),
            recent_repost_authors=[],
            set_trend_snippets=lambda s: None,
            get_session_likes=lambda: 0,
            bump_errors=lambda: None,
            sleep=no_sleep,
            infer_topic=lambda text: "ai",
            topic_multiplier=lambda topic: 0.5,
        )
        asyncio.run(
            SmartEngagementOrchestrator(ports).run(
                SmartEngagementConfig(
                    like_threshold=0.30,
                    max_reposts=0,
                    timeline_pages=1,
                )
            )
        )
        self.assertEqual(liked, [])


class TestEngagementCatchUp(unittest.TestCase):
    def test_eligible_catch_up_windows(self) -> None:
        from engagement_learner import eligible_engagement_catch_up_checks

        now = datetime(2026, 10, 19, 18, 0, 0, tzinfo=timezone.utc)
        action_7h = {
            "uri": "at://x",
            "topic": "ai",
            "ts": (now - timedelta(hours=7)).isoformat(),
            "rewarded_checks": [],
        }
        self.assertEqual(
            eligible_engagement_catch_up_checks(action_7h, now), ["6h"]
        )

        action_30h = {
            "uri": "at://y",
            "topic": "ai",
            "ts": (now - timedelta(hours=30)).isoformat(),
            "rewarded_checks": ["6h"],
        }
        self.assertEqual(
            eligible_engagement_catch_up_checks(action_30h, now), ["24h"]
        )

        done = dict(action_7h, rewarded_checks=["6h"])
        self.assertEqual(eligible_engagement_catch_up_checks(done, now), [])

    def test_catch_up_credits_mocked(self) -> None:
        """Simulate catch-up path: eligible action + mocked metrics → credit."""
        from engagement_learner import (
            EngagementLearner,
            eligible_engagement_catch_up_checks,
        )
        from policy_learner import PolicyLearner

        now = datetime(2026, 10, 19, 18, 0, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            pl = PolicyLearner(
                path=str(Path(tmp) / "e.json"),
                params={},
                arm_keys=["ai", "_other"],
                bootstrap_weights={"ai": 0.5, "_other": 0.5},
            )
            eng = EngagementLearner(pl, TOPIC_GROUPS, enabled=True)
            action = {
                "kind": "like",
                "topic": "ai",
                "uri": "at://liked/1",
                "ts": (now - timedelta(hours=8)).isoformat(),
                "rewarded_checks": [],
            }
            checks = eligible_engagement_catch_up_checks(action, now)
            self.assertIn("6h", checks)
            alpha_before = float(pl.arms["ai"]["alpha"])
            metrics = {"likes": 5, "reposts": 1, "replies": 2}
            for check_id in checks:
                if check_id in action["rewarded_checks"]:
                    continue
                ok = eng.credit(
                    action["topic"],
                    metrics["likes"],
                    metrics["replies"],
                    metrics["reposts"],
                    check_id,
                )
                self.assertTrue(ok)
                action["rewarded_checks"].append(check_id)
            self.assertGreater(float(pl.arms["ai"]["alpha"]), alpha_before)
            self.assertIn("6h", action["rewarded_checks"])


class TestEngagementLearnerLoad(unittest.TestCase):
    def test_load_from_config(self) -> None:
        from engagement_learner import EngagementLearner, OTHER_ARM

        with tempfile.TemporaryDirectory() as tmp:
            cfg = {
                "relevance_settings": {"topic_groups": TOPIC_GROUPS},
                "engagement_learning": {
                    "enabled": True,
                    "state_path": str(Path(tmp) / "learning_state_engagement.json"),
                    "max_arm_share_24h": 0.40,
                    "epsilon": 0.10,
                    "action_credit_delays_hours": [6, 24],
                },
                "learning_parameters": {"reward_scale": 10},
            }
            eng = EngagementLearner.load(
                cfg, base_params=cfg["learning_parameters"]
            )
            self.assertTrue(eng.enabled)
            self.assertIn("ai", eng.learner.arms)
            self.assertIn(OTHER_ARM, eng.learner.arms)
            self.assertEqual(
                eng.action_credit_delays_hours(cfg), [6.0, 24.0]
            )


if __name__ == "__main__":
    unittest.main()
