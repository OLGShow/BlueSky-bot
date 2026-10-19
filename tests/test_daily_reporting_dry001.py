#!/usr/bin/env python3
"""DRY-001: DailyReportingFacade hermetic tests."""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


class FakeMemory:
    def __init__(self) -> None:
        self.ab_results = None


class FakeDryRun:
    def __init__(self) -> None:
        self.saved = False

    def save(self) -> None:
        self.saved = True


class TestDailyReporting(unittest.TestCase):
    def test_acyclic(self) -> None:
        path = APP_DIR / "daily_reporting.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn("bluesky_bot_v2", node.module or "")

    def test_generate_save_and_flush(self) -> None:
        from daily_reporting import DailyReportingFacade

        saved: List[Dict[str, Any]] = []

        def gen(stats, memory, config):
            return {"date": "2026-10-19", "session": dict(stats)}

        def save(report):
            saved.append(report)

        facade = DailyReportingFacade(_generate=gen, _save=save)
        mem = FakeMemory()
        dry = FakeDryRun()
        report = facade.generate_and_save(
            {"likes_given": 1},
            mem,
            {},
            ab_results={"a": 1},
            dry_run=True,
            dry_run_log=dry,
        )
        self.assertEqual(report["date"], "2026-10-19")
        self.assertEqual(len(saved), 1)
        self.assertEqual(mem.ab_results, {"a": 1})
        self.assertTrue(dry.saved)


if __name__ == "__main__":
    unittest.main()
