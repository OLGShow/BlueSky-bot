#!/usr/bin/env python3
"""
HTTP-001 / TEST-001: shared aiohttp ClientSession lifecycle.

Hermetic: AST — no bare ClientSession outside create_http_session helper;
unit — _ensure_http_session close-before-recreate with mocks.
Does not require network or real atproto.

Run:
  python tests/test_http_session_http001.py
  python -m unittest tests.test_http_session_http001
"""

from __future__ import annotations

import ast
import asyncio
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BOT_MODULE_PATH = REPO_ROOT / "bluesky_bot_v2.py"
HTTP_SESSION_MODULE_PATH = REPO_ROOT / "http_session.py"
CREATE_HELPER_NAME = "create_http_session"


def _bot_source() -> str:
    assert BOT_MODULE_PATH.is_file(), f"missing {BOT_MODULE_PATH}"
    return BOT_MODULE_PATH.read_text(encoding="utf-8", errors="replace")


def _http_session_source() -> str:
    assert HTTP_SESSION_MODULE_PATH.is_file(), f"missing {HTTP_SESSION_MODULE_PATH}"
    return HTTP_SESSION_MODULE_PATH.read_text(encoding="utf-8", errors="replace")


def _install_hermetic_import_stubs() -> None:
    if "atproto" not in sys.modules:
        atproto_mod = types.ModuleType("atproto")
        atproto_mod.AsyncClient = mock.MagicMock
        models_mod = types.ModuleType("atproto.models")
        atproto_mod.models = models_mod
        sys.modules["atproto"] = atproto_mod
        sys.modules["atproto.models"] = models_mod
    if "emoji" not in sys.modules:
        sys.modules["emoji"] = types.ModuleType("emoji")


def _load_bot_module():
    _install_hermetic_import_stubs()
    import bluesky_bot_v2 as bot_mod  # noqa: WPS433

    return bot_mod


def _is_aiohttp_client_session_call(call: ast.Call) -> bool:
    """True for aiohttp.ClientSession(...) or ClientSession(...)."""
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == "ClientSession":
        if isinstance(func.value, ast.Name) and func.value.id == "aiohttp":
            return True
    if isinstance(func, ast.Name) and func.id == "ClientSession":
        return True
    return False


def _client_session_calls_outside_create(tree: ast.AST) -> list[tuple[str, int]]:
    """Return (func_name, lineno) for ClientSession calls not in create helper."""
    hits: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        owner = node.name
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and _is_aiohttp_client_session_call(child):
                if owner != CREATE_HELPER_NAME:
                    hits.append((owner, getattr(child, "lineno", -1)))
    return hits


def _client_session_calls_in_module(tree: ast.AST) -> list[tuple[str, int]]:
    """Return (func_name, lineno) for any ClientSession call in the module."""
    hits: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        owner = node.name
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and _is_aiohttp_client_session_call(child):
                hits.append((owner, getattr(child, "lineno", -1)))
    return hits


def _make_bot_shell(bot_mod):
    """Minimal instance without __init__ (no creds / network)."""
    bot = object.__new__(bot_mod.AutonomousBlueskyBotV2)
    bot.http_session = None
    return bot


class TestHttpSessionHttp001Ast(unittest.TestCase):
    def test_no_bare_client_session_in_bot(self):
        tree = ast.parse(_bot_source(), filename=str(BOT_MODULE_PATH))
        hits = _client_session_calls_in_module(tree)
        self.assertEqual(
            hits,
            [],
            f"ClientSession() must not appear in bot; found: {hits}",
        )

    def test_no_bare_client_session_outside_create_helper(self):
        tree = ast.parse(_http_session_source(), filename=str(HTTP_SESSION_MODULE_PATH))
        hits = _client_session_calls_outside_create(tree)
        self.assertEqual(
            hits,
            [],
            f"ClientSession() must only appear in {CREATE_HELPER_NAME}; found: {hits}",
        )

    def test_ensure_helper_present_in_source(self):
        bot_src = _bot_source()
        helper_src = _http_session_source()
        self.assertIn("async def _ensure_http_session", bot_src)
        self.assertIn("force_recreate", bot_src)
        self.assertIn("_create_http_session", bot_src)
        self.assertIn("from http_session import", bot_src)
        self.assertIn(f"def {CREATE_HELPER_NAME}", helper_src)
        self.assertIn("async def ensure_http_session", helper_src)


class TestEnsureHttpSessionHttp001(unittest.TestCase):
    def test_creates_when_session_missing(self):
        bot_mod = _load_bot_module()
        bot = _make_bot_shell(bot_mod)
        fresh = mock.MagicMock()
        fresh.closed = False

        def _create():
            bot.http_session = fresh

        with mock.patch.object(bot, "_create_http_session", side_effect=_create) as create_mock:
            result = asyncio.run(bot._ensure_http_session())
        create_mock.assert_called_once()
        self.assertIs(result, fresh)

    def test_reuses_open_session_without_recreate(self):
        bot_mod = _load_bot_module()
        bot = _make_bot_shell(bot_mod)
        existing = mock.MagicMock()
        existing.closed = False
        bot.http_session = existing

        with mock.patch.object(bot, "_create_http_session") as create_mock:
            result = asyncio.run(bot._ensure_http_session())
        create_mock.assert_not_called()
        self.assertIs(result, existing)

    def test_force_recreate_closes_before_create(self):
        bot_mod = _load_bot_module()
        bot = _make_bot_shell(bot_mod)
        old = mock.MagicMock()
        old.closed = False
        old.close = mock.AsyncMock()
        bot.http_session = old
        fresh = mock.MagicMock()
        fresh.closed = False
        order: list[str] = []

        async def _close():
            order.append("close")

        old.close = _close

        def _create():
            order.append("create")
            bot.http_session = fresh

        with mock.patch.object(bot, "_create_http_session", side_effect=_create):
            result = asyncio.run(bot._ensure_http_session(force_recreate=True))

        self.assertEqual(order, ["close", "create"])
        self.assertIs(result, fresh)

    def test_closed_session_triggers_recreate(self):
        bot_mod = _load_bot_module()
        bot = _make_bot_shell(bot_mod)
        closed = mock.MagicMock()
        closed.closed = True
        bot.http_session = closed
        fresh = mock.MagicMock()
        fresh.closed = False

        def _create():
            bot.http_session = fresh

        with mock.patch.object(bot, "_create_http_session", side_effect=_create) as create_mock:
            result = asyncio.run(bot._ensure_http_session())
        create_mock.assert_called_once()
        self.assertIs(result, fresh)

    def test_raises_when_create_leaves_session_unavailable(self):
        bot_mod = _load_bot_module()
        bot = _make_bot_shell(bot_mod)

        def _create_noop():
            bot.http_session = None

        with mock.patch.object(bot, "_create_http_session", side_effect=_create_noop):
            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(bot._ensure_http_session())
        self.assertIn("unavailable", str(ctx.exception).lower())

    def test_close_error_on_recreate_is_non_fatal(self):
        bot_mod = _load_bot_module()
        bot = _make_bot_shell(bot_mod)
        old = mock.MagicMock()
        old.closed = False
        old.close = mock.AsyncMock(side_effect=RuntimeError("close boom"))
        bot.http_session = old
        fresh = mock.MagicMock()
        fresh.closed = False

        def _create():
            bot.http_session = fresh

        with mock.patch.object(bot, "_create_http_session", side_effect=_create):
            result = asyncio.run(bot._ensure_http_session(force_recreate=True))
        self.assertIs(result, fresh)
        old.close.assert_awaited()


def run_http001_assertions() -> None:
    """Callable from verify/acceptance — raises AssertionError on failure."""
    helper_tree = ast.parse(_http_session_source(), filename=str(HTTP_SESSION_MODULE_PATH))
    hits = _client_session_calls_outside_create(helper_tree)
    assert not hits, f"bare ClientSession outside helper: {hits}"

    bot_tree = ast.parse(_bot_source(), filename=str(BOT_MODULE_PATH))
    bot_hits = _client_session_calls_in_module(bot_tree)
    assert not bot_hits, f"bare ClientSession in bot: {bot_hits}"

    bot_mod = _load_bot_module()
    bot = _make_bot_shell(bot_mod)
    fresh = mock.MagicMock()
    fresh.closed = False

    def _create():
        bot.http_session = fresh

    with mock.patch.object(bot, "_create_http_session", side_effect=_create):
        result = asyncio.run(bot._ensure_http_session())
    assert result is fresh


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    unittest.main(verbosity=2)
