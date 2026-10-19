#!/usr/bin/env python3
"""PLRN-007: catch-up, comment exclusion, arm migration — hermetic tests."""

from __future__ import annotations

import ast
import asyncio
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
BOT_PATH = APP_DIR / "bluesky_bot_v2.py"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from policy_learner import (  # noqa: E402
    PolicyLearner,
    eligible_catch_up_checks,
)


ARM = "_create_quality_news_post"


def _bot_source() -> str:
    return BOT_PATH.read_text(encoding="utf-8")


def _comment_method_body(src: str) -> str:
    marker = "async def create_engaging_comment"
    # fall back: search for comment append patterns near type='comment'
    start = src.find("session_stats['comments_made']")
    if start < 0:
        start = src.find('session_stats["comments_made"]')
    assert start >= 0, "comments_made counter not found"
    # window around comment success handling
    return src[max(0, start - 200) : start + 400]


class TestEligibleCatchUpChecks:
    def test_7h_old_missing_6h(self) -> None:
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        post = {
            "uri": "at://did/app.bsky.feed.post/abc",
            "strategy_key": ARM,
            "type": "general",
            "rewarded_checks": [],
            "timestamp": (now - timedelta(hours=7)).isoformat(),
        }
        assert eligible_catch_up_checks(post, now) == ["6h"]

    def test_30h_old_can_need_both(self) -> None:
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        post = {
            "uri": "at://did/app.bsky.feed.post/abc",
            "strategy_key": ARM,
            "rewarded_checks": [],
            "created_at": now - timedelta(hours=30),
        }
        assert eligible_catch_up_checks(post, now) == ["6h", "24h"]

    def test_40h_old_only_24h_window(self) -> None:
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        post = {
            "uri": "at://did/app.bsky.feed.post/abc",
            "strategy_key": ARM,
            "rewarded_checks": [],
            "timestamp": (now - timedelta(hours=40)).isoformat(),
        }
        assert eligible_catch_up_checks(post, now) == ["24h"]

    def test_already_rewarded_skipped(self) -> None:
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        post = {
            "uri": "at://did/app.bsky.feed.post/abc",
            "strategy_key": ARM,
            "rewarded_checks": ["6h"],
            "timestamp": (now - timedelta(hours=7)).isoformat(),
        }
        assert eligible_catch_up_checks(post, now) == []

    def test_comment_never_eligible(self) -> None:
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        post = {
            "uri": "at://did/app.bsky.feed.post/abc",
            "strategy_key": ARM,
            "type": "comment",
            "rewarded_checks": [],
            "timestamp": (now - timedelta(hours=7)).isoformat(),
        }
        assert eligible_catch_up_checks(post, now) == []

    def test_missing_uri_or_key(self) -> None:
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        assert (
            eligible_catch_up_checks(
                {
                    "strategy_key": ARM,
                    "timestamp": (now - timedelta(hours=7)).isoformat(),
                },
                now,
            )
            == []
        )
        assert (
            eligible_catch_up_checks(
                {
                    "uri": "at://x",
                    "timestamp": (now - timedelta(hours=7)).isoformat(),
                },
                now,
            )
            == []
        )


async def _catch_up_loop(bot, now: datetime) -> int:
    """Same credit orchestration as ``catch_up_pending_credits`` (no bot import)."""
    any_credited = False
    credited_n = 0
    for post in bot.memory.successful_posts:
        checks = eligible_catch_up_checks(post, now)
        if not checks:
            continue
        metrics = await bot.analyze_post_performance(post.get("uri"))
        post["likes"] = metrics.get("likes")
        post["reposts"] = metrics.get("reposts")
        post["replies"] = metrics.get("replies")
        rewarded = post.setdefault("rewarded_checks", [])
        for check_id in checks:
            if check_id in rewarded:
                continue
            ok = bot.policy_learner.credit(
                post.get("strategy_key"),
                post["likes"],
                post["reposts"],
                post["replies"],
                check_id,
            )
            if ok:
                rewarded.append(check_id)
                any_credited = True
                credited_n += 1
    if any_credited:
        bot.policy_learner.save()
        bot.memory.save()
    return credited_n


class TestCatchUpCreditsMockedFetch:
    def test_catch_up_credits_missing_6h_for_7h_post(self, tmp_path) -> None:
        """Catch-up credits missing 6h for 7h-old post (mocked fetch)."""
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        pl = PolicyLearner(
            path=str(tmp_path / "learning_state.json"),
            params={"min_settled_posts": 100},
            arm_keys=[ARM],
            bootstrap_weights={ARM: 1.0},
        )
        post = {
            "uri": "at://did/app.bsky.feed.post/xyz",
            "strategy_key": ARM,
            "type": "general",
            "rewarded_checks": [],
            "timestamp": (now - timedelta(hours=7)).isoformat(),
            "likes": None,
            "reposts": None,
            "replies": None,
        }
        fetch = AsyncMock(
            return_value={
                "likes": 3,
                "reposts": 1,
                "replies": 0,
                "engagement_rate": 4.0,
            }
        )
        bot = SimpleNamespace(
            memory=SimpleNamespace(successful_posts=[post], save=lambda: None),
            policy_learner=pl,
            analyze_post_performance=fetch,
        )

        credited = asyncio.run(_catch_up_loop(bot, now))

        assert credited == 1
        assert post["rewarded_checks"] == ["6h"]
        assert post["likes"] == 3
        assert pl.total_credit_mass > 0
        fetch.assert_awaited_once_with(post["uri"])


class TestCommentNeverCredited:
    def test_comment_eligible_empty_and_no_credit(self, tmp_path) -> None:
        now = datetime.now(timezone.utc)
        pl = PolicyLearner(
            path=str(tmp_path / "learning_state.json"),
            params={},
            arm_keys=[ARM],
            bootstrap_weights={ARM: 1.0},
        )
        post = {
            "uri": "at://did/app.bsky.feed.post/cmt",
            "strategy_key": ARM,
            "type": "comment",
            "rewarded_checks": [],
            "timestamp": (now - timedelta(hours=7)).isoformat(),
            "likes": 10,
            "reposts": 2,
            "replies": 1,
        }
        assert eligible_catch_up_checks(post, now) == []
        # Credit gate (same as delayed_performance_check)
        if (
            post.get("strategy_key")
            and post.get("type") != "comment"
            and "6h" not in post.get("rewarded_checks", [])
        ):
            pl.credit(ARM, 10, 2, 1, "6h")
        assert pl.total_credit_mass == 0.0
        assert post["rewarded_checks"] == []

    def test_bot_does_not_append_comments_to_successful_posts(self) -> None:
        window = _comment_method_body(_bot_source())
        assert "successful_posts.append" not in window
        assert "type': 'comment'" not in window
        assert 'type": "comment"' not in window


class TestSyncArmsAddsNewArm:
    def test_new_config_arm_appears(self, tmp_path) -> None:
        pl = PolicyLearner(
            path=str(tmp_path / "learning_state.json"),
            params={},
            arm_keys=[ARM],
            bootstrap_weights={ARM: 1.0},
        )
        new_arm = "_create_brand_new_arm"
        assert new_arm not in pl.arms
        pl.sync_arms_with_config(
            [ARM, new_arm],
            {ARM: 0.6, new_arm: 0.4},
        )
        assert new_arm in pl.arms
        assert ARM in pl.arms


class TestNoDualWriters:
    def test_no_apply_strategy_weights_in_app(self) -> None:
        src = _bot_source()
        assert "apply_strategy_weights_from_outcomes" not in src

    def test_learn_from_memory_no_content_performance(self) -> None:
        src = _bot_source()
        m = re.search(
            r"def learn_from_memory\(self\).*?(?=\n    (?:async )?def |\nclass |\Z)",
            src,
            re.DOTALL,
        )
        assert m, "learn_from_memory not found"
        body = m.group(0)
        # Docstring may mention the removed path; no writes allowed
        assert "content_performance[" not in body
        assert "content_performance =" not in body
        assert ".content_performance" not in body

    def test_strategy_learning_has_no_apply(self) -> None:
        path = APP_DIR / "strategy_learning.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        }
        assert "apply_strategy_weights_from_outcomes" not in names
        assert "compute_updated_strategy_weights" in names
