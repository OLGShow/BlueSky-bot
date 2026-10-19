#!/usr/bin/env python3
"""HB-001: HeartbeatMonitor hermetic tests."""

from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


class TestHeartbeatNoBotImport(unittest.TestCase):
    def test_acyclic(self) -> None:
        path = APP_DIR / "heartbeat_monitor.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn("bluesky_bot_v2", node.module or "")


class TestHeartbeatMonitor(unittest.TestCase):
    def test_update_and_not_stale(self) -> None:
        from heartbeat_monitor import HeartbeatMonitor

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hb.txt"
            mon = HeartbeatMonitor(str(path))
            now = datetime(2026, 10, 19, 12, 0, 0)
            stamped = mon.update(now=now, pid=1234, status="active")
            self.assertEqual(stamped, now)
            text = path.read_text(encoding="utf-8")
            self.assertIn(now.isoformat(), text)
            self.assertIn("PID: 1234", text)
            self.assertFalse(mon.is_stale(900, now=now + timedelta(minutes=5)))

    def test_stale_after_threshold(self) -> None:
        from heartbeat_monitor import HeartbeatMonitor

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hb.txt"
            mon = HeartbeatMonitor(str(path))
            now = datetime(2026, 10, 19, 12, 0, 0)
            mon.update(now=now, pid=1)
            self.assertTrue(mon.is_stale(900, now=now + timedelta(seconds=901)))

    def test_monitor_status_messages(self) -> None:
        from heartbeat_monitor import HeartbeatMonitor

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hb.txt"
            mon = HeartbeatMonitor(str(path))
            now = datetime(2026, 10, 19, 12, 0, 0)
            mon.update(now=now, pid=1)
            ok, msg = mon.monitor_status(now=now + timedelta(minutes=5))
            self.assertTrue(ok)
            self.assertIn("OK", msg)
            ok2, msg2 = mon.monitor_status(now=now + timedelta(seconds=901))
            self.assertTrue(ok2)
            self.assertIn("ПРЕДУПРЕЖДЕНИЕ", msg2)
            ok3, msg3 = mon.monitor_status(now=now + timedelta(seconds=1201))
            self.assertFalse(ok3)
            self.assertIn("устарел", msg3)


if __name__ == "__main__":
    unittest.main()
