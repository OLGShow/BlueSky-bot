#!/usr/bin/env python3
"""PLRN-012: AgentDecisionLog — write, rotation, payload sanitization."""

from __future__ import annotations

import ast
import json
import random
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
BOT_PATH = APP_DIR / "bluesky_bot_v2.py"
LOG_PATH = APP_DIR / "agent_decision_log.py"
POLICY_PATH = APP_DIR / "policy_learner.py"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from agent_decision_log import (  # noqa: E402
    AgentDecisionLog,
    TEXT_TRUNCATE,
    sanitize_context,
)
from policy_learner import PolicyLearner  # noqa: E402


def _bot_source() -> str:
    return BOT_PATH.read_text(encoding="utf-8")


class TestAgentDecisionLogCore:
    def test_log_writes_jsonl_line(self, tmp_path: Path) -> None:
        path = tmp_path / "agent_decisions.jsonl"
        log = AgentDecisionLog(path=str(path), max_lines=100)
        log.log(
            domain="strategy",
            action="pick_strategy",
            arm="news",
            reason="thompson",
            context={"recent_24h": 3},
        )
        assert path.exists()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["domain"] == "strategy"
        assert entry["action"] == "pick_strategy"
        assert entry["arm"] == "news"
        assert entry["reason"] == "thompson"
        assert entry["context"]["recent_24h"] == 3
        assert "ts" in entry

    def test_rotation_keeps_last_n(self, tmp_path: Path) -> None:
        path = tmp_path / "rotate.jsonl"
        log = AgentDecisionLog(path=str(path), max_lines=5)
        for i in range(12):
            log.log(
                domain="format",
                action="pick_format",
                arm="format_a" if i % 2 == 0 else "format_b",
                reason="thompson",
                context={"i": i},
            )
        lines = [
            ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()
        ]
        assert len(lines) == 5
        idxs = [json.loads(ln)["context"]["i"] for ln in lines]
        assert idxs == [7, 8, 9, 10, 11]

    def test_sanitize_truncates_text_and_strips_secrets(self) -> None:
        huge = "x" * 500
        cleaned = sanitize_context(
            {
                "text": huge,
                "api_token": "super-secret-value",
                "password": "hunter2",
                "nested": {"authorization": "Bearer abc", "ok": 1},
                "uri": "at://did:plc:example/app.bsky.feed.post/" + ("a" * 100),
            }
        )
        assert cleaned["text"] == "x" * TEXT_TRUNCATE
        assert "api_token" not in cleaned
        assert "password" not in cleaned
        assert "authorization" not in cleaned["nested"]
        assert cleaned["nested"]["ok"] == 1
        assert len(cleaned["uri"]) == TEXT_TRUNCATE

    def test_log_drops_huge_payloads(self, tmp_path: Path) -> None:
        path = tmp_path / "safe.jsonl"
        log = AgentDecisionLog(path=str(path), max_lines=100)
        log.log(
            domain="engagement",
            action="like",
            arm="ai",
            reason="topic_multiplier",
            context={
                "text": "T" * 400,
                "access_token": "leak-me",
                "multiplier": 1.25,
            },
        )
        entry = json.loads(path.read_text(encoding="utf-8").strip())
        assert len(entry["context"]["text"]) == TEXT_TRUNCATE
        assert "access_token" not in entry["context"]
        assert entry["context"]["multiplier"] == 1.25
        assert len(path.read_text(encoding="utf-8")) < 2000

    def test_recent_returns_tail(self, tmp_path: Path) -> None:
        path = tmp_path / "recent.jsonl"
        log = AgentDecisionLog(path=str(path), max_lines=100)
        for i in range(5):
            log.log("strategy", "pick", f"arm{i}", reason="thompson", context={"i": i})
        recent = log.recent(2)
        assert len(recent) == 2
        assert recent[0]["arm"] == "arm3"
        assert recent[1]["arm"] == "arm4"


class TestPickArmMeta:
    def test_last_pick_meta_thompson(self, tmp_path: Path) -> None:
        random.seed(0)
        pl = PolicyLearner(
            path=str(tmp_path / "state.json"),
            params={"epsilon": 0.0, "max_arm_share_24h": 1.0},
            arm_keys=["a", "b"],
            bootstrap_weights={"a": 0.5, "b": 0.5},
        )
        arm = pl.pick_arm(["a", "b"], [])
        assert arm in ("a", "b")
        assert pl.last_pick_meta is not None
        assert pl.last_pick_meta["arm"] == arm
        assert pl.last_pick_meta["reason"] == "thompson"

    def test_last_pick_meta_epsilon(self, tmp_path: Path) -> None:
        random.seed(1)
        pl = PolicyLearner(
            path=str(tmp_path / "state.json"),
            params={"epsilon": 1.0, "max_arm_share_24h": 1.0},
            arm_keys=["a", "b"],
            bootstrap_weights={"a": 0.5, "b": 0.5},
        )
        arm = pl.pick_arm(["a", "b"], [])
        assert pl.last_pick_meta["arm"] == arm
        assert pl.last_pick_meta["reason"] == "epsilon"

    def test_last_pick_meta_share_cap(self, tmp_path: Path) -> None:
        random.seed(2)
        pl = PolicyLearner(
            path=str(tmp_path / "state.json"),
            params={"epsilon": 0.0, "max_arm_share_24h": 0.0},
            arm_keys=["a", "b"],
            bootstrap_weights={"a": 0.5, "b": 0.5},
        )
        # every arm share is 0.5 > 0.0 → candidates empty → share_cap fallback
        arm = pl.pick_arm(["a", "b"], ["a", "b"])
        assert pl.last_pick_meta["arm"] == arm
        assert pl.last_pick_meta["reason"] == "share_cap"


class TestBotWiringSource:
    def test_bot_imports_and_wires_decision_log(self) -> None:
        src = _bot_source()
        assert "from agent_decision_log import AgentDecisionLog" in src
        assert "self.decision_log = AgentDecisionLog" in src
        assert 'domain="strategy"' in src
        assert 'domain="format"' in src
        assert 'domain="engagement"' in src
        assert "_log_bandit_pick" in src

    def test_agent_decision_log_no_bot_import(self) -> None:
        tree = ast.parse(LOG_PATH.read_text(encoding="utf-8"), filename=str(LOG_PATH))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "bluesky_bot_v2" not in (node.module or "")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "bluesky_bot_v2" not in alias.name

    def test_policy_learner_sets_last_pick_meta(self) -> None:
        src = POLICY_PATH.read_text(encoding="utf-8")
        assert "last_pick_meta" in src
        assert '"reason"' in src or "'reason'" in src
