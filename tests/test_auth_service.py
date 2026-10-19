#!/usr/bin/env python3
"""Hermetic tests for AuthService (health/media/auth thin-shell extract)."""

from __future__ import annotations

import ast
import asyncio
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from auth_service import AuthPorts, AuthService  # noqa: E402


@dataclass
class _Profile:
    handle: str = "restored.bsky.social"


@dataclass
class FakeAuth:
    handle: str = "bot.bsky.social"
    saved_session: Optional[str] = "sess-token"
    export_string: Optional[str] = "exported-sess"
    restore_ok: bool = True
    login_ok: bool = True
    authenticated: bool = False
    calls: List[str] = field(default_factory=list)

    def as_ports(self) -> AuthPorts:
        fake = self

        async def ensure_http():
            fake.calls.append("ensure_http")

        async def restore_login(session: str):
            fake.calls.append(f"restore:{session}")
            if not fake.restore_ok:
                raise RuntimeError("restore failed")
            return _Profile(handle="restored.bsky.social")

        async def credential_login():
            fake.calls.append("credential_login")
            if not fake.login_ok:
                raise RuntimeError("401 unauthorized")
            return _Profile(handle=fake.handle)

        return AuthPorts(
            ensure_http=ensure_http,
            load_session=lambda: fake.saved_session,
            clear_session=lambda: (
                fake.calls.append("clear_session"),
                setattr(fake, "saved_session", None),
            )[1],
            save_session=lambda ss: (
                fake.calls.append(f"save:{ss}"),
                setattr(fake, "saved_session", ss),
            )[1],
            restore_login=restore_login,
            credential_login=credential_login,
            export_session_string=lambda: fake.export_string,
            set_authenticated=lambda v: (
                fake.calls.append(f"auth:{v}"),
                setattr(fake, "authenticated", bool(v)),
            )[1],
            get_handle=lambda: fake.handle,
        )


class TestAuthServiceNoBotImport(unittest.TestCase):
    def test_module_has_no_bluesky_bot_v2_import(self) -> None:
        path = APP_DIR / "auth_service.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn("bluesky_bot_v2", alias.name)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn("bluesky_bot_v2", node.module or "")


class TestAuthServiceGates(unittest.TestCase):
    def test_restore_failure_clears_and_falls_back(self) -> None:
        fake = FakeAuth(restore_ok=False, login_ok=True)
        svc = AuthService(fake.as_ports())
        ok = asyncio.run(svc.authenticate())
        self.assertTrue(ok)
        self.assertIn("clear_session", fake.calls)
        self.assertIn("credential_login", fake.calls)
        self.assertTrue(fake.authenticated)

    def test_credential_login_failure_returns_false(self) -> None:
        fake = FakeAuth(saved_session=None, login_ok=False)
        svc = AuthService(fake.as_ports())
        ok = asyncio.run(svc.authenticate(force_login=True))
        self.assertFalse(ok)
        self.assertFalse(fake.authenticated)


class TestAuthServiceHappyPath(unittest.TestCase):
    def test_session_restore_happy(self) -> None:
        fake = FakeAuth(restore_ok=True)
        svc = AuthService(fake.as_ports())
        ok = asyncio.run(svc.authenticate())
        self.assertTrue(ok)
        self.assertIn("restore:sess-token", fake.calls)
        self.assertNotIn("credential_login", fake.calls)
        self.assertIn("save:exported-sess", fake.calls)
        self.assertTrue(fake.authenticated)


if __name__ == "__main__":
    unittest.main()
