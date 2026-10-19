#!/usr/bin/env python3
"""PLRN-020: followers-delta reward blending — hermetic tests."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from follower_tracker import FollowerTracker, delta_between  # noqa: E402
from policy_learner import PolicyLearner, compute_reward  # noqa: E402

ARM = "_create_quality_news_post"


def _learner(tmp_path, params=None) -> PolicyLearner:
    return PolicyLearner(
        path=str(tmp_path / "learning_state.json"),
        params=params or {},
        arm_keys=[ARM],
        bootstrap_weights={ARM: 1.0},
    )


class TestComputeRewardFollowers:
    def test_unchanged_when_weight_zero(self) -> None:
        base = compute_reward(2, 1, 1, reward_scale=10)
        with_delta = compute_reward(
            2,
            1,
            1,
            reward_scale=10,
            followers_delta=10,
            followers_weight=0.0,
            followers_scale=5.0,
        )
        assert with_delta == pytest.approx(base)
        assert with_delta == pytest.approx(1.0 - math.exp(-7 / 10))

    def test_unchanged_when_delta_none(self) -> None:
        base = compute_reward(2, 1, 1, reward_scale=10)
        blended = compute_reward(
            2,
            1,
            1,
            reward_scale=10,
            followers_delta=None,
            followers_weight=0.15,
            followers_scale=5.0,
        )
        assert blended == pytest.approx(base)

    def test_positive_delta_increases_reward_vs_zero_delta(self) -> None:
        zero = compute_reward(
            2,
            1,
            1,
            reward_scale=10,
            followers_delta=0,
            followers_weight=0.15,
            followers_scale=5.0,
        )
        positive = compute_reward(
            2,
            1,
            1,
            reward_scale=10,
            followers_delta=5,
            followers_weight=0.15,
            followers_scale=5.0,
        )
        assert positive > zero
        assert 0.0 <= positive < 1.0


class TestFollowerTracker:
    def test_load_save_delta(self, tmp_path) -> None:
        path = tmp_path / "learning_followers.json"
        tracker = FollowerTracker(path=str(path))
        assert tracker.latest() is None

        tracker.record(100, ts="2026-10-19T10:00:00+00:00")
        tracker.record(105, ts="2026-10-19T12:00:00+00:00")
        assert tracker.latest() == 105
        assert path.is_file()

        reloaded = FollowerTracker(path=str(path))
        assert reloaded.latest() == 105
        assert reloaded.delta_since(100) == 5
        assert reloaded.delta_since("2026-10-19T10:00:00+00:00") == 5
        assert delta_between(100, 105) == 5


class TestCreditFollowersDelta:
    def test_credit_accepts_followers_delta(self, tmp_path) -> None:
        pl = _learner(
            tmp_path,
            params={
                "followers_reward_weight": 0.15,
                "followers_scale": 5.0,
            },
        )
        a0 = float(pl.arms[ARM]["alpha"])
        ok = pl.credit(
            ARM,
            likes=2,
            reposts=1,
            replies=1,
            check_id="6h",
            followers_delta=5,
        )
        assert ok is True
        r = compute_reward(
            2,
            1,
            1,
            reward_scale=10,
            followers_delta=5,
            followers_weight=0.15,
            followers_scale=5.0,
        )
        w6 = 0.35
        assert pl.arms[ARM]["alpha"] == pytest.approx(a0 + w6 * r)
        assert pl.arms[ARM]["last_reward"] == pytest.approx(r)

    def test_credit_without_followers_delta_backward_compat(self, tmp_path) -> None:
        pl = _learner(tmp_path)
        ok = pl.credit(ARM, likes=1, reposts=0, replies=0, check_id="6h")
        assert ok is True
        assert pl.arms[ARM]["last_reward"] == pytest.approx(
            compute_reward(1, 0, 0, reward_scale=10)
        )
