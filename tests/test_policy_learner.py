#!/usr/bin/env python3
"""PLRN-002: PolicyLearner bandit core — hermetic tests."""

from __future__ import annotations

import ast
import json
import math
import random
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from policy_learner import PolicyLearner, compute_reward  # noqa: E402


ARM_A = "_create_quality_news_post"
ARM_B = "_create_viral_hot_take"
ARM_C = "_create_quality_tip_post"

BOOTSTRAP = {ARM_A: 0.5, ARM_B: 0.3, ARM_C: 0.2}
ARM_KEYS = [ARM_A, ARM_B, ARM_C]


def _learner(tmp_path, params=None, keys=None, bootstrap=None) -> PolicyLearner:
    path = tmp_path / "learning_state.json"
    return PolicyLearner(
        path=str(path),
        params=params or {},
        arm_keys=keys or list(ARM_KEYS),
        bootstrap_weights=bootstrap or dict(BOOTSTRAP),
    )


class TestComputeReward:
    def test_zero_metrics(self) -> None:
        assert compute_reward(0, 0, 0) == 0.0

    def test_monotonic_in_likes(self) -> None:
        r0 = compute_reward(0, 0, 0)
        r1 = compute_reward(1, 0, 0)
        r5 = compute_reward(5, 0, 0)
        assert r0 < r1 < r5
        assert 0.0 <= r5 < 1.0

    def test_formula_matches_spec(self) -> None:
        likes, replies, reposts, scale = 2, 1, 1, 10
        score = likes + 2 * replies + 3 * reposts
        expected = 1 - math.exp(-score / scale)
        assert compute_reward(likes, replies, reposts, reward_scale=scale) == pytest.approx(
            expected
        )


class TestDualCredit:
    def test_dual_credit_math(self, tmp_path) -> None:
        pl = _learner(tmp_path)
        arm0 = dict(pl.arms[ARM_A])
        a0, b0 = arm0["alpha"], arm0["beta"]

        ok = pl.credit(ARM_A, likes=2, reposts=1, replies=1, check_id="6h")
        assert ok is True
        r = compute_reward(2, 1, 1, reward_scale=10)
        w6 = 0.35
        assert pl.arms[ARM_A]["alpha"] == pytest.approx(a0 + w6 * r)
        assert pl.arms[ARM_A]["beta"] == pytest.approx(b0 + w6 * (1 - r))
        assert pl.arms[ARM_A]["trials"] == pytest.approx(w6)
        assert pl.total_credit_mass == pytest.approx(w6)

        a1 = pl.arms[ARM_A]["alpha"]
        b1 = pl.arms[ARM_A]["beta"]
        t1 = pl.arms[ARM_A]["trials"]
        ok24 = pl.credit(ARM_A, likes=2, reposts=1, replies=1, check_id="24h")
        assert ok24 is True
        w24 = 0.65
        assert pl.arms[ARM_A]["alpha"] == pytest.approx(a1 + w24 * r)
        assert pl.arms[ARM_A]["beta"] == pytest.approx(b1 + w24 * (1 - r))
        assert pl.arms[ARM_A]["trials"] == pytest.approx(t1 + w24)
        assert pl.total_credit_mass == pytest.approx(w6 + w24)

    def test_unknown_arm_returns_false(self, tmp_path) -> None:
        pl = _learner(tmp_path)
        assert pl.credit("missing_arm", 1, 0, 0, "6h") is False

    def test_deltas_ring_buffer(self, tmp_path) -> None:
        pl = _learner(tmp_path, params={"deltas_max": 3})
        for i in range(5):
            pl.credit(ARM_A, likes=i, reposts=0, replies=0, check_id="6h")
        assert len(pl.deltas) == 3


class TestFreezeExport:
    def test_export_bootstrap_until_min_settled(self, tmp_path) -> None:
        pl = _learner(tmp_path, params={"min_settled_posts": 5})
        exported = pl.export_weights()
        total = sum(exported.values())
        assert total == pytest.approx(1.0)
        for key in ARM_KEYS:
            assert exported[key] == pytest.approx(BOOTSTRAP[key])

        pl.total_credit_mass = 4.9
        still_boot = pl.export_weights()
        assert still_boot[ARM_A] == pytest.approx(BOOTSTRAP[ARM_A])

        pl.total_credit_mass = 5.0
        learned = pl.export_weights()
        assert sum(learned.values()) == pytest.approx(1.0)
        assert all(v >= 0.05 - 1e-9 for v in learned.values())

    def test_export_weights_frozen_until_total_credit_mass_ge_min_settled(
        self, tmp_path
    ) -> None:
        """Cold-start freeze: bootstrap until total_credit_mass >= min_settled_posts."""
        min_settled = 5
        pl = _learner(tmp_path, params={"min_settled_posts": min_settled})
        # Skew arm means away from bootstrap so freeze vs unfreeze is detectable.
        pl.arms[ARM_A]["alpha"] = 50.0
        pl.arms[ARM_A]["beta"] = 1.0
        pl.arms[ARM_B]["alpha"] = 1.0
        pl.arms[ARM_B]["beta"] = 50.0

        for mass in (0.0, 1.0, min_settled - 1e-9):
            pl.total_credit_mass = mass
            frozen = pl.export_weights()
            for key in ARM_KEYS:
                assert frozen[key] == pytest.approx(BOOTSTRAP[key])

        pl.total_credit_mass = min_settled
        unfrozen = pl.export_weights()
        assert sum(unfrozen.values()) == pytest.approx(1.0)
        assert unfrozen[ARM_A] != pytest.approx(BOOTSTRAP[ARM_A])
        assert unfrozen[ARM_A] > unfrozen[ARM_B]


class TestDecay:
    def test_soft_decay_toward_prior(self, tmp_path) -> None:
        pl = _learner(tmp_path, params={"decay_every_cycles": 2, "decay_rate": 0.1})
        pl.arms[ARM_A]["alpha"] = 10.0
        pl.arms[ARM_A]["beta"] = 2.0
        prior_a = pl.arms[ARM_A]["prior_alpha"]
        prior_b = pl.arms[ARM_A]["prior_beta"]

        pl.maybe_decay()
        assert pl.cycle_count == 1
        assert pl.arms[ARM_A]["alpha"] == 10.0

        pl.maybe_decay()
        assert pl.cycle_count == 2
        expected_a = 0.9 * 10.0 + 0.1 * prior_a
        expected_b = 0.9 * 2.0 + 0.1 * prior_b
        assert pl.arms[ARM_A]["alpha"] == pytest.approx(expected_a)
        assert pl.arms[ARM_A]["beta"] == pytest.approx(expected_b)


class TestShareCapAndPick:
    def test_share_cap_blocks_dominant_arm(self, tmp_path) -> None:
        pl = _learner(tmp_path, params={"epsilon": 0.0, "max_arm_share_24h": 0.40})
        recent = [ARM_A] * 10
        random.seed(42)
        picks = {pl.pick_arm(ARM_KEYS, recent) for _ in range(30)}
        assert ARM_A not in picks
        assert picks <= {ARM_B, ARM_C}

    def test_share_cap_excludes_arm_when_recent_is_100_percent_one_key(
        self, tmp_path
    ) -> None:
        """Share cap: recent list 100% one arm → that arm excluded from candidates."""
        pl = _learner(tmp_path, params={"epsilon": 0.0, "max_arm_share_24h": 0.40})
        recent = [ARM_B] * 5
        shares = pl._share_map(recent)
        assert shares[ARM_B] == pytest.approx(1.0)
        assert shares[ARM_B] > float(pl.params["max_arm_share_24h"])

        random.seed(7)
        for _ in range(50):
            picked = pl.pick_arm(ARM_KEYS, recent)
            assert picked != ARM_B
            assert picked in (ARM_A, ARM_C)

    def test_record_pick_sets_timestamp(self, tmp_path) -> None:
        pl = _learner(tmp_path)
        assert pl.arms[ARM_A]["last_pick_at"] is None
        pl.record_pick(ARM_A)
        assert pl.arms[ARM_A]["last_pick_at"] is not None

    def test_epsilon_one_picks_only_from_non_blocked(self, tmp_path) -> None:
        """epsilon=1.0: always explore, but only among share-cap candidates."""
        pl = _learner(tmp_path, params={"epsilon": 1.0, "max_arm_share_24h": 0.40})
        recent = [ARM_A] * 10
        random.seed(123)
        for _ in range(40):
            picked = pl.pick_arm(ARM_KEYS, recent)
            assert picked != ARM_A
            assert picked in (ARM_B, ARM_C)

    def test_novelty_idle_arm_wins_under_controlled_rng(
        self, tmp_path, monkeypatch
    ) -> None:
        """Idle arm wins Thompson pick when novelty_bonus tips the sample."""
        pl = _learner(
            tmp_path,
            params={
                "epsilon": 0.0,
                "novelty_idle_days": 14,
                "novelty_bonus": 0.15,
                "max_arm_share_24h": 1.0,
            },
        )
        # Hot arms: recent activity → no novelty bonus.
        pl.arms[ARM_A]["last_pick_at"] = "2026-10-19T12:00:00+00:00"
        pl.arms[ARM_B]["last_pick_at"] = "2026-10-19T12:00:00+00:00"
        # ARM_C idle (no timestamps) → idle_days=inf → +novelty_bonus.
        assert pl.arms[ARM_C]["last_pick_at"] is None
        assert pl.arms[ARM_C]["last_credit_at"] is None

        # Without bonus: A=0.50 > C=0.40; with +0.15: C=0.55 wins.
        samples = iter([0.50, 0.48, 0.40])
        monkeypatch.setattr(random, "random", lambda: 1.0)
        monkeypatch.setattr(random, "betavariate", lambda _a, _b: next(samples))

        picked = pl.pick_arm(ARM_KEYS, [])
        assert picked == ARM_C


class TestLoadSave:
    def test_roundtrip(self, tmp_path) -> None:
        pl = _learner(tmp_path)
        pl.credit(ARM_B, likes=3, reposts=1, replies=0, check_id="6h")
        pl.record_pick(ARM_B)
        pl.cycle_count = 7
        pl.save()

        loaded = PolicyLearner.load(
            path=str(tmp_path / "learning_state.json"),
            params={},
            arm_keys=list(ARM_KEYS),
            bootstrap_weights=dict(BOOTSTRAP),
        )
        assert loaded.cycle_count == 7
        assert loaded.total_credit_mass == pytest.approx(pl.total_credit_mass)
        assert loaded.arms[ARM_B]["alpha"] == pytest.approx(pl.arms[ARM_B]["alpha"])
        assert loaded.arms[ARM_B]["beta"] == pytest.approx(pl.arms[ARM_B]["beta"])
        assert loaded.arms[ARM_B]["last_pick_at"] == pl.arms[ARM_B]["last_pick_at"]
        assert len(loaded.deltas) == 1

        data = json.loads((tmp_path / "learning_state.json").read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert "arms" in data
        assert "bootstrap_weights" in data


class TestSyncArmsAndConfig:
    def test_sync_arms_adds_and_retires(self, tmp_path) -> None:
        pl = _learner(tmp_path)
        pl.credit(ARM_C, likes=1, reposts=0, replies=0, check_id="6h")
        new_keys = [ARM_A, ARM_B, "_new_arm"]
        boot = {ARM_A: 0.4, ARM_B: 0.4, "_new_arm": 0.2}
        pl.sync_arms_with_config(new_keys, boot)
        assert "_new_arm" in pl.arms
        assert ARM_C not in pl.arms
        assert ARM_C in pl.retired_arms

    def test_sync_config_weights_frozen_skips_write(self, tmp_path) -> None:
        cfg = tmp_path / "bot_config.json"
        original = {"post_strategies": {"old": 1.0}}
        cfg.write_text(json.dumps(original), encoding="utf-8")
        pl = _learner(tmp_path, params={"min_settled_posts": 5})
        assert pl.total_credit_mass < 5
        wrote = pl.sync_config_weights(str(cfg))
        assert wrote is False
        assert not (tmp_path / "bot_config.json.bak").exists()
        assert json.loads(cfg.read_text(encoding="utf-8")) == original

    def test_sync_config_weights_bak_after_freeze_lifted(self, tmp_path) -> None:
        cfg = tmp_path / "bot_config.json"
        cfg.write_text(json.dumps({"post_strategies": {"old": 1.0}}), encoding="utf-8")
        pl = _learner(tmp_path, params={"min_settled_posts": 5})
        # Lift freeze: enough credit mass before sync
        pl.total_credit_mass = 5.0
        wrote = pl.sync_config_weights(str(cfg))
        assert wrote is True
        assert (tmp_path / "bot_config.json.bak").is_file()
        bak = json.loads((tmp_path / "bot_config.json.bak").read_text(encoding="utf-8"))
        assert bak["post_strategies"] == {"old": 1.0}
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert sum(data["post_strategies"].values()) == pytest.approx(1.0)
        assert set(data["post_strategies"]) == set(ARM_KEYS)


class TestReportAndWarmStart:
    def test_report_fields(self, tmp_path) -> None:
        pl = _learner(tmp_path)
        pl.credit(ARM_A, likes=1, reposts=0, replies=0, check_id="6h")
        rep = pl.report()
        assert "total_credit_mass" in rep
        assert rep["total_credit_mass"] == pytest.approx(pl.total_credit_mass)
        assert "last_20_deltas" in rep
        assert len(rep["last_20_deltas"]) == 1
        assert "export_weights" in rep
        assert sum(rep["export_weights"].values()) == pytest.approx(1.0)

        arm = rep["arms"][ARM_A]
        for field in ("alpha", "beta", "mean", "trials", "last_reward"):
            assert field in arm
        assert arm["alpha"] == pytest.approx(float(pl.arms[ARM_A]["alpha"]))
        assert arm["beta"] == pytest.approx(float(pl.arms[ARM_A]["beta"]))
        denom = arm["alpha"] + arm["beta"]
        assert arm["mean"] == pytest.approx(arm["alpha"] / denom)
        assert arm["trials"] == pytest.approx(0.35)
        assert arm["last_reward"] == pytest.approx(compute_reward(1, 0, 0))

    def test_write_report_creates_dir_and_file(self, tmp_path) -> None:
        pl = _learner(tmp_path)
        pl.credit(ARM_B, likes=2, reposts=0, replies=0, check_id="6h")
        out = tmp_path / "reports" / "learning_report.json"
        written = pl.write_report(str(out))
        assert written == str(out)
        assert out.is_file()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert ARM_B in data["arms"]
        assert "export_weights" in data
        assert "last_20_deltas" in data

    def test_write_report_uses_param_path(self, tmp_path) -> None:
        report_path = str(tmp_path / "custom" / "out.json")
        pl = _learner(tmp_path, params={"report_path": report_path})
        pl.write_report()
        assert Path(report_path).is_file()

    def test_warm_start_priors(self, tmp_path) -> None:
        pl = _learner(tmp_path, params={"warm_start_strength": 4})
        w = BOOTSTRAP[ARM_A]
        assert pl.arms[ARM_A]["alpha"] == pytest.approx(1 + 4 * w)
        assert pl.arms[ARM_A]["beta"] == pytest.approx(1 + 4 * (1 - w))
        assert pl.arms[ARM_A]["prior_alpha"] == pl.arms[ARM_A]["alpha"]


class TestNoBotImport:
    def test_ast_no_bluesky_bot_v2(self) -> None:
        path = APP_DIR / "policy_learner.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "bluesky_bot_v2" not in alias.name
            elif isinstance(node, ast.ImportFrom):
                assert "bluesky_bot_v2" not in (node.module or "")
