#!/usr/bin/env python3
"""PLRN-022: SafetyGovernor hermetic unit + AST wiring guards.

No bluesky_bot_v2 import — bot wiring checked via AST on source text only.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
BOT_PATH = APP_DIR / "bluesky_bot_v2.py"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from safety_governor import SafetyGovernor, SafetyStatus  # noqa: E402


def _gov(**overrides) -> SafetyGovernor:
    params = {
        "enabled": True,
        "min_budget_ratio": 0.05,
        "followers_shock_abs": 50,
        "max_consecutive_errors": 5,
    }
    params.update(overrides)
    return SafetyGovernor(params)


def _ok_kwargs(**overrides):
    base = {
        "budget_summary": {"hourly": "0/4500", "remaining_hourly": 4500},
        "circuit_open": {"bluesky": False, "ai": False},
        "followers_delta_1h": 0.0,
        "consecutive_errors": 0,
    }
    base.update(overrides)
    return base


class TestSafetyGovernorDefaults:
    def test_all_clear(self) -> None:
        st = _gov().evaluate(**_ok_kwargs())
        assert st.ok is True
        assert st.reasons == []
        assert st.can_credit and st.can_sync_config
        assert st.can_publish and st.can_engagement

    def test_disabled_ignores_signals(self) -> None:
        st = _gov(enabled=False).evaluate(
            **_ok_kwargs(
                circuit_open={"bluesky": True, "ai": True},
                consecutive_errors=99,
                followers_delta_1h=999.0,
                budget_summary={"hourly": "4499/4500", "remaining_hourly": 1},
            )
        )
        assert st.ok is True
        assert st.can_publish and st.can_credit and st.can_sync_config
        assert st.can_engagement


class TestBlueskyCircuitOpen:
    def test_blocks_publish_credit_sync_engagement(self) -> None:
        st = _gov().evaluate(
            **_ok_kwargs(circuit_open={"bluesky": True, "ai": False})
        )
        assert st.ok is False
        assert "bluesky_circuit_open" in st.reasons
        assert st.can_publish is False
        assert st.can_credit is False
        assert st.can_sync_config is False
        assert st.can_engagement is False


class TestAiCircuitOpen:
    def test_blocks_publish_only(self) -> None:
        st = _gov().evaluate(
            **_ok_kwargs(circuit_open={"bluesky": False, "ai": True})
        )
        assert st.ok is False
        assert "ai_circuit_open" in st.reasons
        assert st.can_publish is False
        assert st.can_credit is True
        assert st.can_sync_config is True
        assert st.can_engagement is True  # engagement follows bluesky CB only


class TestBudgetRatio:
    def test_low_hourly_ratio_blocks_publish(self) -> None:
        # remaining 100 / 4500 ≈ 0.022 < 0.05
        st = _gov().evaluate(
            **_ok_kwargs(
                budget_summary={"hourly": "4400/4500", "remaining_hourly": 100}
            )
        )
        assert st.ok is False
        assert st.can_publish is False
        assert st.can_credit is True
        assert any("budget_hourly_ratio" in r for r in st.reasons)

    def test_explicit_remaining_ratio(self) -> None:
        st = _gov(min_budget_ratio=0.1).evaluate(
            **_ok_kwargs(budget_summary={"remaining_ratio": 0.09})
        )
        assert st.can_publish is False

    def test_above_threshold_ok(self) -> None:
        st = _gov().evaluate(
            **_ok_kwargs(
                budget_summary={"hourly": "4000/4500", "remaining_hourly": 500}
            )
        )
        assert st.can_publish is True
        assert st.ok is True


class TestFollowersShock:
    def test_positive_shock_freezes_learning(self) -> None:
        st = _gov().evaluate(**_ok_kwargs(followers_delta_1h=50.0))
        assert st.ok is False
        assert st.can_credit is False
        assert st.can_sync_config is False
        assert st.can_publish is True
        assert any("followers_shock" in r for r in st.reasons)

    def test_negative_shock_freezes_learning(self) -> None:
        st = _gov().evaluate(**_ok_kwargs(followers_delta_1h=-51.0))
        assert st.can_credit is False
        assert st.can_sync_config is False

    def test_below_threshold_ok(self) -> None:
        st = _gov().evaluate(**_ok_kwargs(followers_delta_1h=49.0))
        assert st.ok is True
        assert st.can_credit is True

    def test_none_delta_ignored(self) -> None:
        st = _gov().evaluate(**_ok_kwargs(followers_delta_1h=None))
        assert st.ok is True


class TestConsecutiveErrors:
    def test_at_threshold_blocks_publish_and_credit(self) -> None:
        st = _gov().evaluate(**_ok_kwargs(consecutive_errors=5))
        assert st.ok is False
        assert st.can_publish is False
        assert st.can_credit is False
        assert st.can_sync_config is True
        assert any("consecutive_errors" in r for r in st.reasons)

    def test_below_threshold_ok(self) -> None:
        st = _gov().evaluate(**_ok_kwargs(consecutive_errors=4))
        assert st.ok is True


class TestCombinedRules:
    def test_multiple_reasons_accumulate(self) -> None:
        st = _gov().evaluate(
            **_ok_kwargs(
                circuit_open={"bluesky": True, "ai": True},
                consecutive_errors=10,
            )
        )
        assert st.ok is False
        assert len(st.reasons) >= 2
        assert st.can_publish is False
        assert st.can_credit is False


class TestCircuitBreakerIsOpen:
    def test_is_open_property(self) -> None:
        from resilience_service import CircuitBreaker

        cb = CircuitBreaker("t", failure_threshold=1, recovery_timeout=9999)
        assert cb.is_open is False
        cb.record_failure()
        assert cb.is_open is True
        assert cb.allow_request() is False


class TestFollowerTrackerDelta1h:
    def test_delta_1h_insufficient_history(self, tmp_path) -> None:
        from follower_tracker import FollowerTracker

        path = tmp_path / "f.json"
        tr = FollowerTracker(path=str(path))
        tr.record(100)
        assert tr.delta_1h() is None

    def test_delta_1h_computes(self, tmp_path) -> None:
        from datetime import datetime, timedelta, timezone

        from follower_tracker import FollowerTracker

        path = tmp_path / "f.json"
        tr = FollowerTracker(path=str(path))
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        tr.record(100, ts=(now - timedelta(hours=2)).isoformat())
        tr.record(160, ts=now.isoformat())
        assert tr.delta_1h(now=now) == 60.0


class TestBotAstWiring:
    """AST-only: must not import bluesky_bot_v2."""

    def test_no_bluesky_bot_v2_import_in_this_module(self) -> None:
        src = Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(Path(__file__)))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "") != "bluesky_bot_v2"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "bluesky_bot_v2" not in alias.name

    def test_bot_wires_safety_governor(self) -> None:
        src = BOT_PATH.read_text(encoding="utf-8")
        assert "from learning_orchestrator import LearningOrchestrator" in src
        assert "self.safety_governor = self.learning.safety_governor" in src
        assert "def _safety_status" in src
        assert "can_publish" in src
        assert "can_credit" in src
        assert "can_sync_config" in src or "can_sync" in src
        assert "can_engagement" in src
        orch = (APP_DIR / "learning_orchestrator.py").read_text(encoding="utf-8")
        tree = ast.parse(orch, filename=str(APP_DIR / "learning_orchestrator.py"))
        imported = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "safety_governor":
                names = {a.name for a in node.names}
                assert "SafetyGovernor" in names
                imported = True
        assert imported
        assert "SafetyGovernor(" in orch


class TestSafetyStatusDataclass:
    def test_fields(self) -> None:
        st = SafetyStatus(
            ok=False,
            reasons=["x"],
            can_credit=False,
            can_sync_config=True,
            can_publish=False,
            can_engagement=True,
        )
        assert st.reasons == ["x"]
        assert st.can_sync_config is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
