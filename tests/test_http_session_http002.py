#!/usr/bin/env python3
"""
HTTP-002: shared ClientSession injection into formatter / rich_posts.

Hermetic: no ad-hoc ClientSession when shared injected; closed shared →
RuntimeError; bot inject / reinject; close_session does not close shared.

Run:
  python tests/test_http_session_http002.py
  python -m unittest tests.test_http_session_http002
"""

from __future__ import annotations

import asyncio
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


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
    if "PIL" not in sys.modules:
        pil_mod = types.ModuleType("PIL")
        image_mod = types.ModuleType("PIL.Image")
        image_ops_mod = types.ModuleType("PIL.ImageOps")
        pil_mod.Image = image_mod
        pil_mod.ImageOps = image_ops_mod
        sys.modules["PIL"] = pil_mod
        sys.modules["PIL.Image"] = image_mod
        sys.modules["PIL.ImageOps"] = image_ops_mod


def _load_bot_module():
    _install_hermetic_import_stubs()
    import bluesky_bot_v2 as bot_mod  # noqa: WPS433

    return bot_mod


def _make_bot_shell(bot_mod):
    bot = object.__new__(bot_mod.AutonomousBlueskyBotV2)
    bot.http_session = None
    return bot


class TestFormatterSharedSessionInjection(unittest.TestCase):
    def test_formatter_uses_injected_session_without_creating(self):
        from bluesky_post_formatter import BlueskyPostFormatter

        shared = mock.MagicMock()
        shared.closed = False
        with mock.patch("bluesky_post_formatter.aiohttp.ClientSession") as ctor:
            fmt = BlueskyPostFormatter(http_session=shared)
            session = asyncio.run(fmt.get_session())
            self.assertIs(session, shared)
            ctor.assert_not_called()
            self.assertFalse(fmt._owns_session)

    def test_formatter_raises_after_shared_closed(self):
        from bluesky_post_formatter import BlueskyPostFormatter

        shared = mock.MagicMock()
        shared.closed = False
        fmt = BlueskyPostFormatter(http_session=shared)
        shared.closed = True
        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(fmt.get_session())
        self.assertIn("closed", str(ctx.exception).lower())

    def test_formatter_close_session_does_not_close_shared(self):
        from bluesky_post_formatter import BlueskyPostFormatter

        shared = mock.MagicMock()
        shared.closed = False
        shared.close = mock.AsyncMock()
        fmt = BlueskyPostFormatter(http_session=shared)
        asyncio.run(fmt.close_session())
        shared.close.assert_not_called()
        self.assertIsNone(fmt._session)

    def test_formatter_setter_reinject_after_recreate(self):
        from bluesky_post_formatter import BlueskyPostFormatter

        old = mock.MagicMock()
        old.closed = True
        fresh = mock.MagicMock()
        fresh.closed = False
        fmt = BlueskyPostFormatter(http_session=old)
        with self.assertRaises(RuntimeError):
            asyncio.run(fmt.get_session())
        fmt.set_http_session(fresh)
        session = asyncio.run(fmt.get_session())
        self.assertIs(session, fresh)
        self.assertFalse(fmt._owns_session)


class TestRichPostsSharedSessionInjection(unittest.TestCase):
    def test_rich_uses_injected_session_without_creating(self):
        _install_hermetic_import_stubs()
        from bluesky_rich_posts import BlueskyRichPostCreator

        shared = mock.MagicMock()
        shared.closed = False
        with mock.patch("bluesky_rich_posts.aiohttp.ClientSession") as ctor:
            with mock.patch("bluesky_post_formatter.aiohttp.ClientSession") as fmt_ctor:
                rich = BlueskyRichPostCreator(http_session=shared)
                session = asyncio.run(rich.get_session())
                self.assertIs(session, shared)
                ctor.assert_not_called()
                fmt_ctor.assert_not_called()
                self.assertFalse(rich._owns_session)
                self.assertIs(asyncio.run(rich.formatter.get_session()), shared)
                self.assertFalse(rich.formatter._owns_session)

    def test_rich_raises_after_shared_closed(self):
        _install_hermetic_import_stubs()
        from bluesky_rich_posts import BlueskyRichPostCreator

        shared = mock.MagicMock()
        shared.closed = False
        rich = BlueskyRichPostCreator(http_session=shared)
        shared.closed = True
        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(rich.get_session())
        self.assertIn("closed", str(ctx.exception).lower())

    def test_rich_close_session_does_not_close_shared(self):
        _install_hermetic_import_stubs()
        from bluesky_rich_posts import BlueskyRichPostCreator

        shared = mock.MagicMock()
        shared.closed = False
        shared.close = mock.AsyncMock()
        rich = BlueskyRichPostCreator(http_session=shared)
        asyncio.run(rich.close_session())
        shared.close.assert_not_called()
        self.assertIsNone(rich._session)
        self.assertIsNone(rich.formatter._session)

    def test_rich_propagates_reinject_to_nested_formatter(self):
        _install_hermetic_import_stubs()
        from bluesky_rich_posts import BlueskyRichPostCreator

        old = mock.MagicMock()
        old.closed = True
        fresh = mock.MagicMock()
        fresh.closed = False
        rich = BlueskyRichPostCreator(http_session=old)
        rich.set_http_session(fresh)
        self.assertIs(asyncio.run(rich.get_session()), fresh)
        self.assertIs(asyncio.run(rich.formatter.get_session()), fresh)


class TestBotInjectsFormatterAndRich(unittest.TestCase):
    def test_inject_pushes_session_to_formatter_and_rich(self):
        bot_mod = _load_bot_module()
        bot = _make_bot_shell(bot_mod)
        shared = mock.MagicMock()
        shared.closed = False
        bot.http_session = shared
        bot.pollinations_ai = None
        bot.rss_manager = None
        fmt = mock.MagicMock()
        fmt.set_http_session = mock.MagicMock()
        rich = mock.MagicMock()
        rich.set_http_session = mock.MagicMock()
        bot.formatter = fmt
        bot.rich_creator = rich

        bot._inject_http_session_into_adapters()

        fmt.set_http_session.assert_called_once_with(shared)
        rich.set_http_session.assert_called_once_with(shared)

    def test_ensure_reinjects_into_formatter_and_rich(self):
        bot_mod = _load_bot_module()
        bot = _make_bot_shell(bot_mod)
        fmt = mock.MagicMock()
        fmt.set_http_session = mock.MagicMock()
        rich = mock.MagicMock()
        rich.set_http_session = mock.MagicMock()
        bot.formatter = fmt
        bot.rich_creator = rich
        bot.pollinations_ai = None
        bot.rss_manager = None
        fresh = mock.MagicMock()
        fresh.closed = False

        def _create():
            bot.http_session = fresh

        with mock.patch.object(bot, "_create_http_session", side_effect=_create):
            result = asyncio.run(bot._ensure_http_session(force_recreate=True))

        self.assertIs(result, fresh)
        fmt.set_http_session.assert_called_with(fresh)
        rich.set_http_session.assert_called_with(fresh)


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    unittest.main(verbosity=2)
