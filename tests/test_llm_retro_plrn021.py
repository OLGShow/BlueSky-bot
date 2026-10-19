#!/usr/bin/env python3
"""PLRN-021: LlmRetro weekly allowlisted learning_parameters reflection."""

from __future__ import annotations

import ast
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
RETRO_PATH = APP_DIR / "llm_retro.py"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from llm_retro import ALLOWLIST_KEYS, BOUNDS, LlmRetro  # noqa: E402


class TestParseAndValidate:
    def test_clamps_out_of_range(self) -> None:
        retro = LlmRetro()
        patch = retro.parse_and_validate(
            {
                "learning_parameters": {
                    "epsilon": 9.0,
                    "reward_scale": -5,
                    "weight_min": 0.001,
                    "max_arm_share_24h": 0.99,
                }
            }
        )
        assert patch["epsilon"] == BOUNDS["epsilon"][1]
        assert patch["reward_scale"] == BOUNDS["reward_scale"][0]
        assert patch["weight_min"] == BOUNDS["weight_min"][0]
        assert patch["max_arm_share_24h"] == BOUNDS["max_arm_share_24h"][1]

    def test_rejects_unknown_keys(self) -> None:
        retro = LlmRetro()
        patch = retro.parse_and_validate(
            {
                "learning_parameters": {
                    "epsilon": 0.2,
                    "post_interval": 999,
                    "evil_key": 1,
                    "min_settled_posts": 100,
                }
            }
        )
        assert "epsilon" in patch
        assert "post_interval" not in patch
        assert "evil_key" not in patch
        assert "min_settled_posts" not in patch
        assert set(patch.keys()).issubset(ALLOWLIST_KEYS)

    def test_flat_dict_also_works(self) -> None:
        retro = LlmRetro()
        patch = retro.parse_and_validate({"decay_rate": 0.01, "unknown": 1})
        assert patch == {"decay_rate": 0.01}


class TestShouldRun:
    def test_false_if_ran_yesterday(self, tmp_path: Path) -> None:
        state = tmp_path / "learning_retro_state.json"
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        state.write_text(
            json.dumps({"last_ran": yesterday}),
            encoding="utf-8",
        )
        retro = LlmRetro(state_path=str(state))
        assert retro.should_run(interval_days=7) is False

    def test_true_if_never(self, tmp_path: Path) -> None:
        state = tmp_path / "learning_retro_state.json"
        retro = LlmRetro(state_path=str(state))
        assert retro.should_run(interval_days=7) is True

    def test_true_if_interval_elapsed(self, tmp_path: Path) -> None:
        state = tmp_path / "learning_retro_state.json"
        old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        state.write_text(json.dumps({"last_ran": old}), encoding="utf-8")
        retro = LlmRetro(state_path=str(state))
        assert retro.should_run(interval_days=7) is True


class TestApplyPatch:
    def test_only_touches_learning_parameters(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "bot_config.json"
        original = {
            "post_strategies": {"arm_a": 0.7, "arm_b": 0.3},
            "learning_parameters": {
                "epsilon": 0.10,
                "reward_scale": 10,
                "state_path": "learning_state.json",
            },
            "other_section": {"keep": True},
        }
        cfg_path.write_text(json.dumps(original, indent=2), encoding="utf-8")

        retro = LlmRetro()
        ok = retro.apply_patch(
            str(cfg_path),
            {"epsilon": 0.25, "post_strategies": {"hacked": 1}},
        )
        assert ok is True

        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert data["post_strategies"] == original["post_strategies"]
        assert data["other_section"] == {"keep": True}
        assert data["learning_parameters"]["epsilon"] == 0.25
        assert data["learning_parameters"]["reward_scale"] == 10
        assert data["learning_parameters"]["state_path"] == "learning_state.json"
        assert "post_strategies" not in data["learning_parameters"]

        bak = json.loads((tmp_path / "bot_config.json.bak").read_text(encoding="utf-8"))
        assert bak["learning_parameters"]["epsilon"] == 0.10

    def test_empty_patch_noop(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "bot_config.json"
        cfg_path.write_text(
            json.dumps({"learning_parameters": {"epsilon": 0.1}}),
            encoding="utf-8",
        )
        retro = LlmRetro()
        assert retro.apply_patch(str(cfg_path), {}) is False
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert data["learning_parameters"]["epsilon"] == 0.1


class TestSuggestionReport:
    def test_writes_report_with_applied_flag(self, tmp_path: Path) -> None:
        reports = tmp_path / "reports"
        retro = LlmRetro(report_dir=str(reports), dry_run=True)
        now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
        path = retro.write_suggestion_report(
            {"epsilon": 0.2},
            raw={"learning_parameters": {"epsilon": 0.2}},
            applied=False,
            now=now,
        )
        assert path.endswith("retro_2026-10-19.json")
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        assert payload["applied"] is False
        assert payload["dry_run"] is True
        assert payload["patch"]["epsilon"] == 0.2


class TestAstIsolation:
    def test_no_bluesky_bot_v2_import(self) -> None:
        tree = ast.parse(RETRO_PATH.read_text(encoding="utf-8"), filename=str(RETRO_PATH))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "bluesky_bot_v2" not in (node.module or "")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "bluesky_bot_v2" not in alias.name


def test_propose_noop_on_empty_llm(tmp_path: Path) -> None:
    import asyncio

    retro = LlmRetro(state_path=str(tmp_path / "state.json"))

    async def empty_fn(_prompt: str) -> dict:
        return {}

    assert asyncio.run(retro.propose(empty_fn, {}, [])) == {}

    async def fail_fn(_prompt: str) -> dict:
        raise RuntimeError("boom")

    assert asyncio.run(retro.propose(fail_fn, {}, [])) == {}
