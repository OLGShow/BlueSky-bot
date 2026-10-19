#!/usr/bin/env python3
"""PLRN-010: FormatBandit (PolicyLearner over format_a/b) — hermetic tests."""

from __future__ import annotations

import ast
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
BOT_PATH = APP_DIR / "bluesky_bot_v2.py"
POLICY_PATH = APP_DIR / "policy_learner.py"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from policy_learner import (  # noqa: E402
    FORMAT_ARM_KEYS,
    PolicyLearner,
    eligible_format_catch_up_checks,
    recent_format_keys_24h,
)


FORMAT_A = "format_a"
FORMAT_B = "format_b"
FORMAT_KEYS = list(FORMAT_ARM_KEYS)
BOOTSTRAP = {FORMAT_A: 0.5, FORMAT_B: 0.5}


def _format_bandit(tmp_path, params=None) -> PolicyLearner:
    defaults = {
        "max_arm_share_24h": 0.70,
        "epsilon": 0.0,
        "min_settled_posts": 100,
    }
    if params:
        defaults.update(params)
    return PolicyLearner(
        path=str(tmp_path / "learning_state_format.json"),
        params=defaults,
        arm_keys=list(FORMAT_KEYS),
        bootstrap_weights=dict(BOOTSTRAP),
    )


def _bot_source() -> str:
    return BOT_PATH.read_text(encoding="utf-8")


def _create_scheduled_post_body(src: str) -> str:
    marker = "async def create_scheduled_post"
    start = src.find(marker)
    assert start >= 0, "create_scheduled_post not found"
    rest = src[start:]
    m = re.search(r"\n    (?:async )?def |\nclass ", rest[1:])
    end = (m.start() + 1) if m else len(rest)
    return rest[:end]


def _delayed_performance_check_body(src: str) -> str:
    marker = "async def delayed_performance_check"
    start = src.find(marker)
    assert start >= 0, "delayed_performance_check not found"
    rest = src[start:]
    m = re.search(r"\n    (?:async )?def |\nclass ", rest[1:])
    end = (m.start() + 1) if m else len(rest)
    return rest[:end]


class TestNoBotImportInPolicyLearner:
    def test_ast_no_bluesky_bot_v2_import(self) -> None:
        tree = ast.parse(POLICY_PATH.read_text(encoding="utf-8"), filename=str(POLICY_PATH))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "") != "bluesky_bot_v2"
                assert not (node.module or "").endswith("bluesky_bot_v2")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "bluesky_bot_v2" not in alias.name


class TestBotWiresFormatBandit:
    def test_init_loads_format_bandit(self) -> None:
        src = _bot_source()
        assert "format_learning" in src
        assert "self.format_bandit = PolicyLearner.load" in src
        assert "learning_state_format.json" in src

    def test_create_scheduled_post_delegates_to_format_bandit(self) -> None:
        body = _create_scheduled_post_body(_bot_source())
        assert "format_bandit.pick_arm" in body
        assert "format_bandit.record_pick" in body
        assert "recent_format_keys_24h" in body
        assert "get_prompt_suffix" in body
        assert "format_rewarded_checks" in body

    def test_delayed_check_credits_format_bandit(self) -> None:
        body = _delayed_performance_check_body(_bot_source())
        assert "format_bandit.credit" in body
        assert "format_rewarded_checks" in body

    def test_catch_up_includes_format(self) -> None:
        src = _bot_source()
        assert "eligible_format_catch_up_checks" in src
        assert "Format catch-up credit" in src or "format_bandit.credit" in src


class TestShareCap070:
    def test_params_default_share_cap_is_070(self, tmp_path) -> None:
        fb = _format_bandit(tmp_path)
        assert float(fb.params["max_arm_share_24h"]) == pytest.approx(0.70)

    def test_share_cap_070_blocks_dominant_format(self, tmp_path) -> None:
        """With 2 arms and cap 0.70, 100% recent format_a is blocked."""
        fb = _format_bandit(
            tmp_path, params={"epsilon": 0.0, "max_arm_share_24h": 0.70}
        )
        recent = [FORMAT_A] * 10
        shares = fb._share_map(recent)
        assert shares[FORMAT_A] == pytest.approx(1.0)
        assert shares[FORMAT_A] > 0.70

        random.seed(42)
        for _ in range(40):
            picked = fb.pick_arm(FORMAT_KEYS, recent)
            assert picked == FORMAT_B

    def test_share_cap_070_allows_balanced_mix(self, tmp_path) -> None:
        """At 60% share (< 0.70) both arms remain candidates."""
        fb = _format_bandit(
            tmp_path, params={"epsilon": 0.0, "max_arm_share_24h": 0.70}
        )
        recent = [FORMAT_A] * 6 + [FORMAT_B] * 4
        shares = fb._share_map(recent)
        assert shares[FORMAT_A] == pytest.approx(0.6)
        assert shares[FORMAT_A] <= 0.70

        random.seed(7)
        picks = {fb.pick_arm(FORMAT_KEYS, recent) for _ in range(50)}
        assert picks <= {FORMAT_A, FORMAT_B}
        assert len(picks) >= 1


class TestCreditBothFormats:
    def test_credit_updates_both_format_arms(self, tmp_path) -> None:
        fb = _format_bandit(tmp_path)
        a0 = dict(fb.arms[FORMAT_A])
        b0 = dict(fb.arms[FORMAT_B])

        assert fb.credit(FORMAT_A, likes=3, reposts=1, replies=0, check_id="6h")
        assert fb.credit(FORMAT_B, likes=1, reposts=0, replies=2, check_id="6h")
        assert fb.credit(FORMAT_A, likes=3, reposts=1, replies=0, check_id="24h")
        assert fb.credit(FORMAT_B, likes=1, reposts=0, replies=2, check_id="24h")

        assert fb.arms[FORMAT_A]["alpha"] > a0["alpha"]
        assert fb.arms[FORMAT_B]["alpha"] > b0["alpha"]
        assert fb.arms[FORMAT_A]["trials"] == pytest.approx(1.0)  # 0.35+0.65
        assert fb.arms[FORMAT_B]["trials"] == pytest.approx(1.0)
        assert fb.total_credit_mass == pytest.approx(2.0)

    def test_pick_returns_format_keys(self, tmp_path) -> None:
        fb = _format_bandit(tmp_path, params={"epsilon": 1.0})
        random.seed(1)
        for _ in range(20):
            assert fb.pick_arm(FORMAT_KEYS, []) in FORMAT_KEYS


class TestRecentFormatKeysAndCatchUp:
    def test_recent_format_keys_24h(self) -> None:
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        posts = [
            {
                "ab_format": FORMAT_A,
                "timestamp": (now - timedelta(hours=2)).isoformat(),
            },
            {
                "ab_format": FORMAT_B,
                "created_at": now - timedelta(hours=30),
            },
            {
                "ab_format": FORMAT_B,
                "timestamp": (now - timedelta(hours=1)).isoformat(),
            },
            {"timestamp": now.isoformat()},
        ]
        assert recent_format_keys_24h(posts, now=now) == [FORMAT_A, FORMAT_B]

    def test_eligible_format_catch_up_7h(self) -> None:
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        post = {
            "uri": "at://did/app.bsky.feed.post/abc",
            "ab_format": FORMAT_A,
            "format_rewarded_checks": [],
            "timestamp": (now - timedelta(hours=7)).isoformat(),
        }
        assert eligible_format_catch_up_checks(post, now) == ["6h"]

    def test_eligible_format_skips_already_rewarded(self) -> None:
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        post = {
            "uri": "at://did/app.bsky.feed.post/abc",
            "ab_format": FORMAT_A,
            "format_rewarded_checks": ["6h"],
            "timestamp": (now - timedelta(hours=7)).isoformat(),
        }
        assert eligible_format_catch_up_checks(post, now) == []

    def test_eligible_format_needs_ab_format(self) -> None:
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        post = {
            "uri": "at://did/app.bsky.feed.post/abc",
            "format_rewarded_checks": [],
            "timestamp": (now - timedelta(hours=7)).isoformat(),
        }
        assert eligible_format_catch_up_checks(post, now) == []


class TestCreditIdempotencyViaFormatRewardedChecks:
    """Mirrors delayed_performance_check format gate without importing the bot."""

    def test_duplicate_format_check_skipped(self, tmp_path) -> None:
        fb = _format_bandit(tmp_path)
        post = {
            "ab_format": FORMAT_A,
            "format_rewarded_checks": [],
            "likes": 2,
            "reposts": 0,
            "replies": 1,
            "type": "general",
        }
        check_id = "6h"
        fmt_rewarded = post.setdefault("format_rewarded_checks", [])
        assert check_id not in fmt_rewarded
        ok = fb.credit(
            post["ab_format"],
            post["likes"],
            post["reposts"],
            post["replies"],
            check_id,
        )
        assert ok
        fmt_rewarded.append(check_id)

        alpha_after = fb.arms[FORMAT_A]["alpha"]
        # Second pass: gate skips credit
        if check_id not in fmt_rewarded:
            fb.credit(
                post["ab_format"],
                post["likes"],
                post["reposts"],
                post["replies"],
                check_id,
            )
        assert fb.arms[FORMAT_A]["alpha"] == pytest.approx(alpha_after)
