#!/usr/bin/env python3
"""LearningOrchestrator first-slice: from_config + AST isolation."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
ORCH_PATH = APP_DIR / "learning_orchestrator.py"
BOT_PATH = APP_DIR / "bluesky_bot_v2.py"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from learning_orchestrator import LearningOrchestrator  # noqa: E402
from policy_learner import PolicyLearner  # noqa: E402
from safety_governor import SafetyStatus  # noqa: E402


def _minimal_config(tmp_path: Path) -> dict:
    return {
        "post_strategies": {
            "_create_quality_news_post": 0.5,
            "_create_personal_opinion_post": 0.5,
        },
        "learning_parameters": {
            "state_path": str(tmp_path / "learning_state.json"),
            "followers_state_path": str(tmp_path / "learning_followers.json"),
            "decision_log_path": str(tmp_path / "reports" / "agent_decisions.jsonl"),
            "decision_log_max_lines": 100,
        },
        "format_learning": {
            "enabled": True,
            "state_path": str(tmp_path / "learning_state_format.json"),
            "max_arm_share_24h": 0.70,
        },
        "engagement_learning": {
            "enabled": True,
            "state_path": str(tmp_path / "learning_state_engagement.json"),
        },
        "relevance_settings": {"topic_groups": {"tech": {"keywords": ["ai"], "weight": 0.1}}},
        "safety_governor": {"enabled": True},
        "llm_retro": {
            "enabled": False,
            "state_path": str(tmp_path / "learning_retro_state.json"),
            "report_dir": str(tmp_path / "reports"),
            "dry_run": True,
        },
    }


class TestFromConfig:
    def test_builds_stack_with_tmp_paths(self, tmp_path: Path) -> None:
        cfg = _minimal_config(tmp_path)
        config_path = str(tmp_path / "bot_config.json")
        orch = LearningOrchestrator.from_config(cfg, config_path=config_path)

        assert orch.config_path == config_path
        assert isinstance(orch.policy_learner, PolicyLearner)
        assert isinstance(orch.format_bandit, PolicyLearner)
        assert orch.engagement_learner is not None
        assert orch.follower_tracker is not None
        assert orch.llm_retro is not None
        assert orch.safety_governor is not None
        assert orch.decision_log is not None
        assert set(orch.policy_learner.arms.keys()) >= set(cfg["post_strategies"])
        assert set(orch.format_bandit.arms.keys()) == {"format_a", "format_b"}

    def test_format_bandit_disabled(self, tmp_path: Path) -> None:
        cfg = _minimal_config(tmp_path)
        cfg["format_learning"]["enabled"] = False
        orch = LearningOrchestrator.from_config(
            cfg, config_path=str(tmp_path / "bot_config.json")
        )
        assert orch.format_bandit is None

    def test_decision_log_path_override(self, tmp_path: Path) -> None:
        cfg = _minimal_config(tmp_path)
        override = str(tmp_path / "custom_decisions.jsonl")
        orch = LearningOrchestrator.from_config(
            cfg,
            config_path=str(tmp_path / "bot_config.json"),
            decision_log_path=override,
        )
        assert orch.decision_log.path == override

    def test_log_pick_writes_line(self, tmp_path: Path) -> None:
        cfg = _minimal_config(tmp_path)
        orch = LearningOrchestrator.from_config(
            cfg, config_path=str(tmp_path / "bot_config.json")
        )
        orch.log_pick(
            domain="strategy",
            action="pick_strategy",
            arm="news",
            reason="thompson",
            context={"n": 1},
        )
        path = Path(orch.decision_log.path)
        assert path.exists()
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 1

    def test_safety_status_delegates(self, tmp_path: Path) -> None:
        cfg = _minimal_config(tmp_path)
        orch = LearningOrchestrator.from_config(
            cfg, config_path=str(tmp_path / "bot_config.json")
        )
        status = orch.safety_status(
            budget_summary=None,
            circuit_open=None,
            followers_delta_1h=None,
            consecutive_errors=0,
        )
        assert isinstance(status, SafetyStatus)
        assert status.ok is True


class TestAstIsolation:
    def test_no_bluesky_bot_v2_import(self) -> None:
        tree = ast.parse(
            ORCH_PATH.read_text(encoding="utf-8"), filename=str(ORCH_PATH)
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "bluesky_bot_v2" not in (node.module or "")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "bluesky_bot_v2" not in alias.name

    def test_bot_wires_learning_orchestrator(self) -> None:
        src = BOT_PATH.read_text(encoding="utf-8")
        assert "from learning_orchestrator import LearningOrchestrator" in src
        assert "LearningOrchestrator.from_config" in src
        assert "self.learning = LearningOrchestrator.from_config" in src
        assert "self.policy_learner = self.learning.policy_learner" in src
        assert "self.safety_governor = self.learning.safety_governor" in src
