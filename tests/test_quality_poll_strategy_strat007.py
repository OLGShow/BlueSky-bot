#!/usr/bin/env python3
"""
STRAT-007: QualityPollStrategy — hermetic tests with fake PollStrategyPorts.

No network, atproto, or AutonomousBlueskyBotV2.

Covers:
  - success path (topic → LLM → create_poll with options/duration/content_type)
  - empty structured content → fallback text still calls create_poll
  - strategies package has no bluesky_bot_v2 import (AST)

Run:
  python tests/test_quality_poll_strategy_strat007.py
  python -m unittest tests.test_quality_poll_strategy_strat007
"""

from __future__ import annotations

import ast
import asyncio
import sys
import unittest
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

STRATEGIES_DIR = APP_DIR / "strategies"
FORBIDDEN = "bluesky_bot_v2"

FIXED_TOPIC = ("tabs vs spaces", ("Табы", "Пробелы"))


class FakeContent:
    def __init__(
        self,
        payload: Optional[Mapping[str, str]] = None,
        *,
        empty: bool = False,
    ):
        self.empty = empty
        self.payload = payload or {
            "post_text": "Eternal debate — what do you pick for formatting?",
            "hashtags": "#poll #coding #holywar",
        }
        self.calls: List[tuple] = []

    async def generate(
        self, prompt: str, *, model_key: str = "creative"
    ) -> Optional[Mapping[str, str]]:
        self.calls.append((prompt, model_key))
        if self.empty:
            return None
        return dict(self.payload)


class FakePoll:
    def __init__(self) -> None:
        self.calls: List[dict] = []

    def create_poll(
        self,
        *,
        question: str,
        options: Sequence[str],
        duration_hours: int = 24,
        content_type: str = "poll",
    ) -> dict:
        call = {
            "question": question,
            "options": list(options),
            "duration_hours": duration_hours,
            "content_type": content_type,
        }
        self.calls.append(call)
        return {"kind": "poll", **call}


def _make_ports(*, content_empty: bool = False):
    from strategies.ports import PollStrategyPorts

    content = FakeContent(empty=content_empty)
    poll = FakePoll()
    ports = PollStrategyPorts(content=content, poll=poll)
    return ports, content, poll


class TestStrategiesPackageNoBotImport(unittest.TestCase):
    def test_strategies_package_has_no_bluesky_bot_v2_import(self) -> None:
        self.assertTrue(STRATEGIES_DIR.is_dir(), f"missing {STRATEGIES_DIR}")
        py_files = sorted(STRATEGIES_DIR.glob("*.py"))
        self.assertTrue(py_files, "strategies package has no .py files")

        for path in py_files:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(
                            FORBIDDEN,
                            alias.name,
                            f"{path.name} imports {alias.name}",
                        )
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    self.assertNotIn(
                        FORBIDDEN,
                        mod,
                        f"{path.name} imports from {mod}",
                    )


class TestQualityPollStrategy(unittest.TestCase):
    def test_success_path_create_poll_parity(self) -> None:
        from strategies.poll_post import STRATEGY_NAME, QualityPollStrategy

        self.assertEqual(STRATEGY_NAME, "_create_quality_poll_post")

        ports, content, poll = _make_ports()
        strategy = QualityPollStrategy(ports)

        with patch(
            "strategies.poll_post.random.choice",
            return_value=FIXED_TOPIC,
        ):
            result = asyncio.run(strategy.create())

        self.assertEqual(result["kind"], "poll")
        self.assertEqual(len(content.calls), 1)
        self.assertEqual(content.calls[0][1], "creative")
        self.assertIn("tabs vs spaces", content.calls[0][0])

        self.assertEqual(len(poll.calls), 1)
        call = poll.calls[0]
        self.assertEqual(call["options"], ["Табы", "Пробелы"])
        self.assertEqual(call["duration_hours"], 24)
        self.assertEqual(call["content_type"], "poll")
        self.assertIn("Eternal debate", call["question"])
        self.assertIn("#poll #coding #holywar", call["question"])

    def test_empty_structured_content_uses_fallback_then_create_poll(self) -> None:
        from strategies.poll_post import QualityPollStrategy

        ports, content, poll = _make_ports(content_empty=True)
        strategy = QualityPollStrategy(ports)

        with patch(
            "strategies.poll_post.random.choice",
            return_value=FIXED_TOPIC,
        ):
            result = asyncio.run(strategy.create())

        self.assertEqual(result["kind"], "poll")
        self.assertEqual(len(content.calls), 1)
        self.assertEqual(len(poll.calls), 1)
        call = poll.calls[0]
        self.assertEqual(call["options"], ["Табы", "Пробелы"])
        self.assertEqual(call["duration_hours"], 24)
        self.assertEqual(call["content_type"], "poll")
        self.assertIn("Время для вашего мнения", call["question"])
        self.assertIn("#опрос #мнение #IT", call["question"])


if __name__ == "__main__":
    unittest.main()
