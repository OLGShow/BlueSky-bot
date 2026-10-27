#!/usr/bin/env python3
"""CYCLE-001: BotCycleRunner.tick sequencing — hermetic tests."""

from __future__ import annotations

import ast
import asyncio
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


class RecordingPorts:
    """Fake BotCyclePorts that records call order."""

    def __init__(
        self,
        *,
        engagement_mode: str = "open",
        in_window: bool = True,
        health: str = "ok",
        recovery: bool = True,
    ) -> None:
        self.calls: List[str] = []
        self._engagement_mode = engagement_mode
        self._in_window = in_window
        self._health = health
        self._recovery = recovery

    def update_heartbeat(self) -> None:
        self.calls.append("heartbeat")

    def reset_consecutive_errors(self) -> None:
        self.calls.append("reset_errors")

    def engagement_mode(self) -> str:
        return self._engagement_mode

    async def smart_engagement(self) -> None:
        self.calls.append("engagement")

    async def follow_strategy(self) -> None:
        self.calls.append("follow")

    def follow_every_n_cycles(self) -> int:
        return 2

    def post_interval_minutes(self) -> float:
        return 60.0

    def is_posting_window(self) -> bool:
        return self._in_window

    def is_engagement_window(self) -> bool:
        return True

    def is_follow_window(self) -> bool:
        return True

    async def create_scheduled_post(self) -> None:
        self.calls.append("post")

    async def update_posts_with_real_metrics(self) -> None:
        self.calls.append("metrics")

    def learn_from_memory(self) -> None:
        self.calls.append("learn")

    def trim_in_memory_caches(self) -> None:
        self.calls.append("trim")

    def sync_duplicate_caches_to_memory(self) -> None:
        self.calls.append("sync_caches")

    def save_memory(self) -> None:
        self.calls.append("save")

    def session_stats(self) -> Mapping[str, Any]:
        return {"posts": 1}

    def daily_post_counts(self) -> tuple[int, int]:
        return (1, 10)

    def cleanup_old_content_hashes(self) -> None:
        self.calls.append("cleanup_hashes")

    def cleanup_old_commented_posts(self) -> None:
        self.calls.append("cleanup_comments")

    def compact_action_ledger(self) -> None:
        self.calls.append("compact")

    def cleanup_log_budget(self) -> tuple[int, int]:
        self.calls.append("log_budget")
        return (0, 0)

    def rotate_rss(self) -> None:
        self.calls.append("rss")

    def generate_and_save_daily_report(self) -> None:
        self.calls.append("daily_report")

    async def analyze_post_diversity(self) -> None:
        self.calls.append("diversity")

    async def health_monitor(self) -> Mapping[str, Any]:
        self.calls.append("health")
        return {"overall_health": self._health}

    async def emergency_recovery(self) -> bool:
        self.calls.append("recovery")
        return self._recovery

    def persist_session(self) -> None:
        self.calls.append("persist")


class TestBotCycleNoBotImport(unittest.TestCase):
    def test_module_has_no_bluesky_bot_v2_import(self) -> None:
        path = APP_DIR / "bot_cycle.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn("bluesky_bot_v2", alias.name)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn("bluesky_bot_v2", node.module or "")


class TestBotCycleRunnerTick(unittest.TestCase):
    def test_typical_tick_engagement_then_post_skip_learn(self) -> None:
        from bot_cycle import BotCycleRunner

        ports = RecordingPorts()
        runner = BotCycleRunner(ports)
        fixed_now = datetime(2026, 10, 19, 12, 0, 0)
        last_post = fixed_now - timedelta(hours=2)

        result = asyncio.run(
            runner.tick(cycle_count=1, last_post_time=last_post, now=lambda: fixed_now)
        )

        self.assertEqual(
            ports.calls[:4],
            ["heartbeat", "reset_errors", "engagement", "post"],
        )
        self.assertNotIn("learn", ports.calls)
        self.assertNotIn("follow", ports.calls)
        self.assertEqual(result.last_post_time, fixed_now)
        self.assertFalse(result.stop)

    def test_cycle0_learn_and_follow_cadence(self) -> None:
        from bot_cycle import BotCycleRunner

        ports = RecordingPorts()
        runner = BotCycleRunner(ports)
        fixed_now = datetime(2026, 10, 19, 12, 0, 0)
        last_post = fixed_now - timedelta(hours=2)

        asyncio.run(
            runner.tick(cycle_count=0, last_post_time=last_post, now=lambda: fixed_now)
        )

        self.assertIn("follow", ports.calls)
        self.assertIn("metrics", ports.calls)
        self.assertIn("learn", ports.calls)
        self.assertIn("save", ports.calls)

    def test_follow_every_other_cycle(self) -> None:
        from bot_cycle import BotCycleRunner

        ports = RecordingPorts()
        runner = BotCycleRunner(ports)
        fixed_now = datetime(2026, 10, 19, 12, 0, 0)
        last_post = fixed_now - timedelta(hours=2)

        asyncio.run(
            runner.tick(cycle_count=2, last_post_time=last_post, now=lambda: fixed_now)
        )
        self.assertIn("follow", ports.calls)

        ports2 = RecordingPorts()
        asyncio.run(
            BotCycleRunner(ports2).tick(
                cycle_count=1, last_post_time=last_post, now=lambda: fixed_now
            )
        )
        self.assertNotIn("follow", ports2.calls)

    def test_mention_only_skips_engagement(self) -> None:
        from bot_cycle import BotCycleRunner

        ports = RecordingPorts(engagement_mode="mention_only")
        runner = BotCycleRunner(ports)
        fixed_now = datetime(2026, 10, 19, 12, 0, 0)

        asyncio.run(
            runner.tick(
                cycle_count=1,
                last_post_time=fixed_now - timedelta(hours=2),
                now=lambda: fixed_now,
            )
        )

        self.assertNotIn("engagement", ports.calls)
        self.assertIn("post", ports.calls)

    def test_critical_health_stop(self) -> None:
        from bot_cycle import BotCycleRunner

        ports = RecordingPorts(health="critical", recovery=False)
        runner = BotCycleRunner(ports)
        fixed_now = datetime(2026, 10, 19, 12, 0, 0)

        result = asyncio.run(
            runner.tick(
                cycle_count=20,
                last_post_time=fixed_now,
                now=lambda: fixed_now,
            )
        )

        self.assertIn("health", ports.calls)
        self.assertIn("recovery", ports.calls)
        self.assertTrue(result.stop)


if __name__ == "__main__":
    unittest.main()
