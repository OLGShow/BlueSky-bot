#!/usr/bin/env python3
"""Wave 2: schedule_windows hermetic tests."""

from __future__ import annotations

import ast
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


class TestScheduleWindows(unittest.TestCase):
    def test_acyclic(self) -> None:
        tree = ast.parse((APP_DIR / "schedule_windows.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn("bluesky_bot_v2", node.module or "")

    def test_empty_allows(self) -> None:
        from schedule_windows import is_allowed

        self.assertTrue(is_allowed({}, "post"))
        self.assertTrue(is_allowed({"timezone": "UTC"}, "engagement"))

    def test_quiet_blocks(self) -> None:
        from schedule_windows import is_allowed

        now = datetime(2026, 10, 27, 3, 0, tzinfo=timezone.utc)
        sched = {"timezone": "UTC", "quiet_hours": [2, 3, 4, 5]}
        self.assertFalse(is_allowed(sched, "post", now=now))
        self.assertTrue(
            is_allowed(sched, "post", now=datetime(2026, 10, 27, 12, tzinfo=timezone.utc))
        )

    def test_engagement_kind_specific(self) -> None:
        from schedule_windows import is_allowed

        now = datetime(2026, 10, 27, 3, 0, tzinfo=timezone.utc)
        sched = {
            "timezone": "UTC",
            "quiet_hours": [],
            "engagement_quiet_hours": [2, 3, 4, 5],
            "follow_quiet_hours": [2, 3, 4, 5],
        }
        self.assertTrue(is_allowed(sched, "post", now=now))
        self.assertFalse(is_allowed(sched, "engagement", now=now))
        self.assertFalse(is_allowed(sched, "follow", now=now))

    def test_active_window_wrap(self) -> None:
        from schedule_windows import is_allowed

        sched = {"timezone": "UTC", "active_windows": [[22, 6]]}
        self.assertTrue(
            is_allowed(
                sched, "post", now=datetime(2026, 10, 27, 23, tzinfo=timezone.utc)
            )
        )
        self.assertFalse(
            is_allowed(
                sched, "post", now=datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
            )
        )


class TestBotCycleWindows(unittest.TestCase):
    def test_skips_engagement_and_follow_in_quiet(self) -> None:
        import asyncio
        from datetime import timedelta
        from typing import Any, List, Mapping

        from bot_cycle import BotCycleRunner

        class QuietPorts:
            def __init__(self) -> None:
                self.calls: List[str] = []

            def update_heartbeat(self) -> None:
                self.calls.append("heartbeat")

            def reset_consecutive_errors(self) -> None:
                pass

            def engagement_mode(self) -> str:
                return "open"

            async def smart_engagement(self) -> None:
                self.calls.append("engagement")

            async def follow_strategy(self) -> None:
                self.calls.append("follow")

            def follow_every_n_cycles(self) -> int:
                return 2

            def post_interval_minutes(self) -> float:
                return 60.0

            def is_posting_window(self) -> bool:
                return True

            def is_engagement_window(self) -> bool:
                return False

            def is_follow_window(self) -> bool:
                return False

            async def create_scheduled_post(self) -> None:
                self.calls.append("post")

            async def update_posts_with_real_metrics(self) -> None:
                pass

            def learn_from_memory(self) -> None:
                pass

            def trim_in_memory_caches(self) -> None:
                pass

            def sync_duplicate_caches_to_memory(self) -> None:
                pass

            def save_memory(self) -> None:
                pass

            def session_stats(self) -> Mapping[str, Any]:
                return {}

            def daily_post_counts(self) -> tuple[int, int]:
                return (0, 10)

            def cleanup_old_content_hashes(self) -> None:
                pass

            def cleanup_old_commented_posts(self) -> None:
                pass

            def compact_action_ledger(self) -> None:
                pass

            def cleanup_log_budget(self) -> tuple[int, int]:
                return (0, 0)

            def rotate_rss(self) -> None:
                pass

            def generate_and_save_daily_report(self) -> None:
                pass

            async def analyze_post_diversity(self) -> None:
                pass

            async def health_monitor(self) -> Mapping[str, Any]:
                return {"overall_health": "ok"}

            async def emergency_recovery(self) -> bool:
                return True

            def persist_session(self) -> None:
                pass

        ports = QuietPorts()
        fixed = datetime(2026, 10, 27, 12, 0, 0)
        asyncio.run(
            BotCycleRunner(ports).tick(
                cycle_count=0,
                last_post_time=fixed - timedelta(hours=2),
                now=lambda: fixed,
            )
        )
        self.assertNotIn("engagement", ports.calls)
        self.assertNotIn("follow", ports.calls)
        self.assertIn("post", ports.calls)


if __name__ == "__main__":
    unittest.main()
