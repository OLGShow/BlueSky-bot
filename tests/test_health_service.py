#!/usr/bin/env python3
"""Hermetic tests for HealthService (health/media/auth thin-shell extract)."""

from __future__ import annotations

import ast
import asyncio
import sys
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from health_service import HealthPorts, HealthService  # noqa: E402


@dataclass
class FakeHealth:
    bluesky_ok: bool = True
    internet_ok: bool = True
    memory_mb: float = 100.0
    posts: List[Dict[str, Any]] = field(default_factory=list)
    likes_given: int = 1
    auth_ok: bool = True
    emergency_post: Any = field(default_factory=lambda: {"ok": True})
    calls: List[str] = field(default_factory=list)

    def as_ports(self) -> HealthPorts:
        fake = self

        def _make_resp(ok: bool) -> AsyncMock:
            resp = AsyncMock()
            resp.status = 200 if ok else 503
            resp.__aenter__ = AsyncMock(return_value=resp)
            resp.__aexit__ = AsyncMock(return_value=False)
            return resp

        def session_get(url: str, timeout: int = 10):
            if "bsky" in url:
                return _make_resp(fake.bluesky_ok)
            if "httpbin" in url:
                return _make_resp(fake.internet_ok)
            return _make_resp(True)

        session = MagicMock()
        session.get = MagicMock(side_effect=session_get)

        async def reinit_http():
            fake.calls.append("reinit_http")

        async def create_emergency():
            fake.calls.append("create_emergency_post")
            return fake.emergency_post

        async def authenticate():
            fake.calls.append("authenticate")
            return fake.auth_ok

        return HealthPorts(
            get_http_session=lambda: session,
            get_memory_mb=lambda: fake.memory_mb,
            get_successful_posts=lambda: fake.posts,
            get_likes_given=lambda: fake.likes_given,
            cleanup_content_hashes=lambda: fake.calls.append("cleanup_hashes"),
            cleanup_commented_posts=lambda: fake.calls.append("cleanup_comments"),
            reinit_http=reinit_http,
            create_emergency_post=create_emergency,
            authenticate=authenticate,
            save_memory=lambda: fake.calls.append("save_memory"),
        )


class TestHealthServiceNoBotImport(unittest.TestCase):
    def test_module_has_no_bluesky_bot_v2_import(self) -> None:
        path = APP_DIR / "health_service.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn("bluesky_bot_v2", alias.name)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn("bluesky_bot_v2", node.module or "")


class TestHealthServiceGates(unittest.TestCase):
    def test_api_down_triggers_http_reinit(self) -> None:
        fake = FakeHealth(bluesky_ok=False, internet_ok=True)
        svc = HealthService(fake.as_ports())
        status = asyncio.run(svc.health_monitor())
        self.assertIn("http_session_reinitialized", status["auto_recovery_actions"])
        self.assertIn(status["overall_health"], ("warning", "critical", "degraded"))
        self.assertEqual(status["network_status"], "degraded")

    def test_emergency_recovery_auth_failure(self) -> None:
        fake = FakeHealth(auth_ok=False)
        svc = HealthService(fake.as_ports())
        ok = asyncio.run(svc.emergency_recovery())
        self.assertFalse(ok)
        self.assertIn("save_memory", fake.calls)
        self.assertIn("authenticate", fake.calls)


class TestHealthServiceHappyPath(unittest.TestCase):
    def test_healthy_when_network_ok(self) -> None:
        recent = datetime.now() - timedelta(hours=1)
        fake = FakeHealth(
            bluesky_ok=True,
            internet_ok=True,
            posts=[{"timestamp": recent}],
        )
        svc = HealthService(fake.as_ports())
        status = asyncio.run(svc.health_monitor())
        self.assertEqual(status["overall_health"], "healthy")
        self.assertEqual(status["network_status"], "healthy")
        self.assertEqual(status["auto_recovery_actions"], [])

    def test_emergency_recovery_happy(self) -> None:
        fake = FakeHealth(auth_ok=True)
        svc = HealthService(fake.as_ports())
        ok = asyncio.run(svc.emergency_recovery())
        self.assertTrue(ok)
        self.assertEqual(
            fake.calls,
            [
                "save_memory",
                "cleanup_hashes",
                "cleanup_comments",
                "reinit_http",
                "authenticate",
            ],
        )


if __name__ == "__main__":
    unittest.main()
