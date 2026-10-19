#!/usr/bin/env python3
"""
VER-001: Bluesky credentials fail-fast (empty / whitespace / placeholder).

Hermetic: mocks env + load_dotenv; never hits live Bluesky/OpenRouter APIs.
Does not require real API keys.

Covers:
  - AutonomousBlueskyBotV2.__init__: strip + raise on empty/whitespace creds
  - main(): sys.exit(1) on missing / whitespace / placeholder (your-) creds
  - no interactive prompt (input) in the bot module

Run:
  python tests/test_bluesky_creds_failfast_ver001.py
  python -m unittest tests.test_bluesky_creds_failfast_ver001
"""

from __future__ import annotations

import ast
import asyncio
import os
import sys
import types
import unittest
from pathlib import Path
from typing import Dict, Optional
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BOT_MODULE_PATH = REPO_ROOT / "bluesky_bot_v2.py"

# Non-placeholder dummies — never used for live network; only for "would proceed" guards.
_DUMMY_HANDLE = "test-bot.bsky.social"
_DUMMY_PASSWORD = "app-password-not-a-placeholder"


def _env_without_bluesky(**overrides: str) -> Dict[str, str]:
    """Build env dict without live Bluesky creds; apply overrides."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("BLUESKY_HANDLE", "BLUESKY_PASSWORD")
    }
    env.update(overrides)
    return env


def _install_hermetic_import_stubs() -> None:
    """Stub optional heavy deps so bluesky_bot_v2 imports without atproto/emoji."""
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
    import bluesky_bot_v2 as bot_mod  # noqa: WPS433 — deferred for hermetic isolation

    return bot_mod


def _bot_source() -> str:
    assert BOT_MODULE_PATH.is_file(), f"missing {BOT_MODULE_PATH}"
    return BOT_MODULE_PATH.read_text(encoding="utf-8", errors="replace")


class TestInitCredsFailFastVer001(unittest.TestCase):
    """__init__ strip + empty check — raises before any network client use."""

    def test_init_raises_when_handle_missing(self):
        bot_mod = _load_bot_module()
        env = _env_without_bluesky(BLUESKY_PASSWORD=_DUMMY_PASSWORD)
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError) as ctx:
                bot_mod.AutonomousBlueskyBotV2()
        self.assertIn("BLUESKY_HANDLE", str(ctx.exception))
        self.assertIn("BLUESKY_PASSWORD", str(ctx.exception))

    def test_init_raises_when_password_missing(self):
        bot_mod = _load_bot_module()
        env = _env_without_bluesky(BLUESKY_HANDLE=_DUMMY_HANDLE)
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError) as ctx:
                bot_mod.AutonomousBlueskyBotV2()
        self.assertIn("BLUESKY_HANDLE", str(ctx.exception))

    def test_init_raises_when_handle_whitespace_only(self):
        bot_mod = _load_bot_module()
        env = _env_without_bluesky(
            BLUESKY_HANDLE="   \t  ",
            BLUESKY_PASSWORD=_DUMMY_PASSWORD,
        )
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError):
                bot_mod.AutonomousBlueskyBotV2()

    def test_init_raises_when_password_whitespace_only(self):
        bot_mod = _load_bot_module()
        env = _env_without_bluesky(
            BLUESKY_HANDLE=_DUMMY_HANDLE,
            BLUESKY_PASSWORD="  \n ",
        )
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError):
                bot_mod.AutonomousBlueskyBotV2()

    def test_init_raises_when_both_empty_strings(self):
        bot_mod = _load_bot_module()
        env = _env_without_bluesky(BLUESKY_HANDLE="", BLUESKY_PASSWORD="")
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError):
                bot_mod.AutonomousBlueskyBotV2()


class TestMainCredsFailFastVer001(unittest.TestCase):
    """main() must fail-fast and never construct the bot or acquire the lock."""

    def _run_main_expect_no_bot(
        self,
        *,
        handle: Optional[str],
        password: Optional[str],
        omit_keys: bool = False,
    ) -> None:
        bot_mod = _load_bot_module()
        if omit_keys:
            env = _env_without_bluesky()
        else:
            overrides: Dict[str, str] = {}
            if handle is not None:
                overrides["BLUESKY_HANDLE"] = handle
            if password is not None:
                overrides["BLUESKY_PASSWORD"] = password
            env = _env_without_bluesky(**overrides)

        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.object(bot_mod, "load_dotenv") as load_dotenv_mock:
                with mock.patch.object(bot_mod, "AutonomousBlueskyBotV2") as bot_cls:
                    with mock.patch.object(bot_mod, "SingleInstanceLock") as lock_cls:
                        with mock.patch("builtins.input") as input_mock:
                            with self.assertRaises(SystemExit) as cm:
                                asyncio.run(bot_mod.main())
                            self.assertEqual(cm.exception.code, 1)
                            load_dotenv_mock.assert_called()
                            bot_cls.assert_not_called()
                            lock_cls.assert_not_called()
                            input_mock.assert_not_called()

    def test_main_failfast_missing_both(self):
        self._run_main_expect_no_bot(handle=None, password=None, omit_keys=True)

    def test_main_failfast_empty_handle(self):
        self._run_main_expect_no_bot(handle="", password=_DUMMY_PASSWORD)

    def test_main_failfast_empty_password(self):
        self._run_main_expect_no_bot(handle=_DUMMY_HANDLE, password="")

    def test_main_failfast_whitespace_handle(self):
        self._run_main_expect_no_bot(handle="   ", password=_DUMMY_PASSWORD)

    def test_main_failfast_whitespace_password(self):
        self._run_main_expect_no_bot(handle=_DUMMY_HANDLE, password=" \t ")

    def test_main_failfast_placeholder_handle(self):
        self._run_main_expect_no_bot(
            handle="your-bot.bsky.social",
            password=_DUMMY_PASSWORD,
        )

    def test_main_failfast_placeholder_password(self):
        self._run_main_expect_no_bot(
            handle=_DUMMY_HANDLE,
            password="your-app-password",
        )

    def test_main_failfast_both_placeholders(self):
        self._run_main_expect_no_bot(
            handle="your-bot.bsky.social",
            password="your-app-password",
        )

    def test_main_proceeds_past_gate_with_non_placeholder_creds(self):
        """Gate opens for non-placeholder values; bot construct is mocked (no network)."""
        bot_mod = _load_bot_module()
        env = _env_without_bluesky(
            BLUESKY_HANDLE=_DUMMY_HANDLE,
            BLUESKY_PASSWORD=_DUMMY_PASSWORD,
        )

        lock_instance = mock.MagicMock()
        bot_instance = mock.MagicMock()
        bot_instance.run_bot_cycle = mock.AsyncMock()
        bot_instance.shutdown = mock.AsyncMock()

        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.object(bot_mod, "load_dotenv"):
                with mock.patch.object(
                    bot_mod, "AutonomousBlueskyBotV2", return_value=bot_instance
                ) as bot_cls:
                    with mock.patch.object(
                        bot_mod, "SingleInstanceLock", return_value=lock_instance
                    ) as lock_cls:
                        with mock.patch("builtins.input") as input_mock:
                            asyncio.run(bot_mod.main())
                            lock_cls.assert_called_once()
                            lock_instance.acquire.assert_called_once()
                            bot_cls.assert_called_once()
                            bot_instance.run_bot_cycle.assert_awaited()
                            bot_instance.shutdown.assert_awaited()
                            lock_instance.release.assert_called()
                            input_mock.assert_not_called()


class TestCredsFailFastSourceVer001(unittest.TestCase):
    """Hermetic source/AST guards — no import of heavy bot deps required for these."""

    def test_no_input_calls_in_bot_module(self):
        tree = ast.parse(_bot_source(), filename=str(BOT_MODULE_PATH))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "input":
                    self.fail("bluesky_bot_v2.py must not call input() for credentials")
                if isinstance(func, ast.Attribute) and func.attr == "input":
                    self.fail("bluesky_bot_v2.py must not call *.input() for credentials")

    def test_init_strips_bluesky_env(self):
        src = _bot_source()
        self.assertIn("BLUESKY_HANDLE", src)
        self.assertIn("BLUESKY_PASSWORD", src)
        # strip() must be applied to both creds in __init__
        self.assertRegex(
            src,
            r"self\.handle\s*=\s*\(os\.getenv\(['\"]BLUESKY_HANDLE['\"]\)\s*or\s*['\"]['\"]\)\.strip\(\)",
        )
        self.assertRegex(
            src,
            r"self\.password\s*=\s*\(os\.getenv\(['\"]BLUESKY_PASSWORD['\"]\)\s*or\s*['\"]['\"]\)\.strip\(\)",
        )

    def test_main_has_placeholder_gate(self):
        src = _bot_source()
        self.assertIn("creds_placeholder", src)
        self.assertIn("'your-' in handle", src)
        self.assertIn("'your-' in password", src)
        self.assertIn("creds_missing", src)
        self.assertIn("sys.exit(1)", src)


def run_creds_failfast_ver001_assertions() -> None:
    """Callable from verify_bot / acceptance nets — raises AssertionError on failure."""
    src = _bot_source()
    assert "creds_placeholder" in src, "main() must gate placeholder Bluesky creds"
    assert "'your-' in handle" in src, "placeholder gate must check handle"
    assert "'your-' in password" in src, "placeholder gate must check password"
    assert ".strip()" in src, "creds must be stripped before empty checks"
    assert "sys.exit(1)" in src, "main() must exit 1 on bad creds / lock failure"

    tree = ast.parse(src, filename=str(BOT_MODULE_PATH))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "input":
                raise AssertionError("bluesky_bot_v2.py must not call input()")

    bot_mod = _load_bot_module()
    env = _env_without_bluesky()
    with mock.patch.dict(os.environ, env, clear=True):
        with mock.patch.object(bot_mod, "load_dotenv"):
            with mock.patch.object(bot_mod, "AutonomousBlueskyBotV2") as bot_cls:
                with mock.patch.object(bot_mod, "SingleInstanceLock") as lock_cls:
                    try:
                        asyncio.run(bot_mod.main())
                        raise AssertionError("main must sys.exit(1) without creds")
                    except SystemExit as exc:
                        assert exc.code == 1, f"expected exit code 1, got {exc.code!r}"
                    assert not bot_cls.called, "main must not build bot without creds"
                    assert not lock_cls.called, "main must not take lock without creds"

    with mock.patch.dict(
        os.environ,
        _env_without_bluesky(
            BLUESKY_HANDLE="your-bot.bsky.social",
            BLUESKY_PASSWORD="your-app-password",
        ),
        clear=True,
    ):
        with mock.patch.object(bot_mod, "load_dotenv"):
            with mock.patch.object(bot_mod, "AutonomousBlueskyBotV2") as bot_cls:
                try:
                    asyncio.run(bot_mod.main())
                    raise AssertionError("main must sys.exit(1) on placeholder creds")
                except SystemExit as exc:
                    assert exc.code == 1, f"expected exit code 1, got {exc.code!r}"
                assert not bot_cls.called, "main must reject placeholder creds"

    with mock.patch.dict(
        os.environ,
        _env_without_bluesky(BLUESKY_HANDLE="  ", BLUESKY_PASSWORD=_DUMMY_PASSWORD),
        clear=True,
    ):
        try:
            bot_mod.AutonomousBlueskyBotV2()
            raise AssertionError("__init__ must raise on whitespace handle")
        except ValueError:
            pass


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    unittest.main(verbosity=2)
