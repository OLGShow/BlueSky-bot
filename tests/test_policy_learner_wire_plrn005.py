#!/usr/bin/env python3
"""PLRN-005: PolicyLearner wired into bot — hermetic AST + helper tests."""

from __future__ import annotations

import ast
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
BOT_PATH = APP_DIR / "bluesky_bot_v2.py"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from policy_learner import (  # noqa: E402
    PolicyLearner,
    recent_strategy_keys_24h,
)


def _bot_source() -> str:
    return BOT_PATH.read_text(encoding="utf-8")


def _create_scheduled_post_body(src: str) -> str:
    marker = "async def create_scheduled_post"
    start = src.find(marker)
    assert start >= 0, "create_scheduled_post not found"
    # next top-level method at same indent after this def
    rest = src[start:]
    m = re.search(r"\n    (?:async )?def |\nclass ", rest[1:])
    end = (m.start() + 1) if m else len(rest)
    return rest[:end]


class TestBotAstGuards:
    def test_no_bot_learning_module_import(self) -> None:
        tree = ast.parse(_bot_source(), filename=str(BOT_PATH))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "") != "bot_learning_module"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "bot_learning_module" not in alias.name

    def test_no_analyze_performance_and_learn_call(self) -> None:
        assert "analyze_performance_and_learn" not in _bot_source()

    def test_no_apply_strategy_weights_call_site(self) -> None:
        src = _bot_source()
        assert "apply_strategy_weights_from_outcomes" not in src
        assert "_update_strategy_weights_from_memory" not in src

    def test_no_topic_boost_in_create_scheduled_post(self) -> None:
        body = _create_scheduled_post_body(_bot_source())
        assert "1.3" not in body
        assert "Audience memory" not in body

    def test_create_scheduled_post_uses_pick_arm(self) -> None:
        body = _create_scheduled_post_body(_bot_source())
        assert "policy_learner.pick_arm" in body
        assert "record_pick" in body
        assert "post_strategy_registry.resolve" in body

    def test_policy_learner_import_present(self) -> None:
        src = _bot_source()
        assert "from policy_learner import" in src
        assert "PolicyLearner" in src
        assert "recent_strategy_keys_24h" in src
        assert "eligible_catch_up_checks" in src


class TestRecentStrategyKeys24h:
    def test_filters_by_window_and_key(self) -> None:
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        posts = [
            {
                "strategy_key": "arm_a",
                "timestamp": (now - timedelta(hours=2)).isoformat(),
            },
            {
                "strategy_key": "arm_b",
                "created_at": now - timedelta(hours=30),
            },
            {
                "strategy_key": "arm_c",
                "timestamp": (now - timedelta(hours=1)).isoformat(),
            },
            {"timestamp": now.isoformat()},  # no strategy_key
        ]
        keys = recent_strategy_keys_24h(posts, now=now)
        assert keys == ["arm_a", "arm_c"]

    def test_accepts_naive_datetime(self) -> None:
        now = datetime(2026, 10, 19, 12, 0)
        posts = [
            {
                "strategy_key": "arm_a",
                "created_at": now - timedelta(hours=3),
            }
        ]
        assert recent_strategy_keys_24h(posts, now=now) == ["arm_a"]


class TestCreditIdempotencyHelper:
    """Mirrors delayed_performance_check credit gate without importing the bot."""

    def test_duplicate_check_id_skipped(self, tmp_path) -> None:
        arm = "_create_quality_news_post"
        pl = PolicyLearner(
            path=str(tmp_path / "learning_state.json"),
            params={"min_settled_posts": 100},
            arm_keys=[arm],
            bootstrap_weights={arm: 1.0},
        )
        post = {
            "strategy_key": arm,
            "type": "general",
            "rewarded_checks": [],
            "likes": 2,
            "reposts": 1,
            "replies": 0,
        }
        check_id = "6h"

        def _maybe_credit() -> bool:
            rewarded = post.setdefault("rewarded_checks", [])
            if (
                post.get("strategy_key")
                and post.get("type") != "comment"
                and check_id not in rewarded
            ):
                ok = pl.credit(
                    post["strategy_key"],
                    post["likes"],
                    post["reposts"],
                    post["replies"],
                    check_id,
                )
                if ok:
                    rewarded.append(check_id)
                return ok
            return False

        assert _maybe_credit() is True
        mass = pl.total_credit_mass
        assert _maybe_credit() is False
        assert pl.total_credit_mass == pytest.approx(mass)
        assert post["rewarded_checks"] == ["6h"]

    def test_comment_type_never_credited(self, tmp_path) -> None:
        arm = "_create_quality_news_post"
        pl = PolicyLearner(
            path=str(tmp_path / "learning_state.json"),
            params={},
            arm_keys=[arm],
            bootstrap_weights={arm: 1.0},
        )
        post = {
            "strategy_key": arm,
            "type": "comment",
            "rewarded_checks": [],
            "likes": 5,
            "reposts": 0,
            "replies": 0,
        }
        check_id = "6h"
        if (
            post.get("strategy_key")
            and post.get("type") != "comment"
            and check_id not in post.get("rewarded_checks", [])
        ):
            pl.credit(arm, 5, 0, 0, check_id)
        assert pl.total_credit_mass == 0.0
        assert post["rewarded_checks"] == []
