#!/usr/bin/env python3
"""
SEC-001 / TEST-001: content hash uses MD5 with usedforsecurity=False.

Hermetic: AST source guard + unbound method call (no network, no atproto).
Duplicate-detection digest must stay stable (algorithm unchanged).

Run:
  python tests/test_content_hash_sec001.py
  python -m unittest tests.test_content_hash_sec001
"""

from __future__ import annotations

import ast
import hashlib
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

BOT_MODULE_PATH = APP_DIR / "bluesky_bot_v2.py"


def _bot_source() -> str:
    assert BOT_MODULE_PATH.is_file(), f"missing {BOT_MODULE_PATH}"
    return BOT_MODULE_PATH.read_text(encoding="utf-8", errors="replace")


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
    import bluesky_bot_v2 as bot_mod  # noqa: WPS433

    return bot_mod


def _find_generate_content_hash_md5_calls(tree: ast.AST) -> list[ast.Call]:
    """Return hashlib.md5(...) Call nodes inside _generate_content_hash."""
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "_generate_content_hash":
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            # hashlib.md5(...)
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "md5"
                and isinstance(func.value, ast.Name)
                and func.value.id == "hashlib"
            ):
                calls.append(child)
    return calls


def _call_has_usedforsecurity_false(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg != "usedforsecurity":
            continue
        val = kw.value
        if isinstance(val, ast.Constant) and val.value is False:
            return True
        # ast.NameConstant for older Python ASTs is unlikely on 3.10+; keep Constant.
    return False


class TestContentHashSec001Ast(unittest.TestCase):
    """Source/AST guards — no bot import required."""

    def test_md5_call_has_usedforsecurity_false(self):
        tree = ast.parse(_bot_source(), filename=str(BOT_MODULE_PATH))
        calls = _find_generate_content_hash_md5_calls(tree)
        self.assertTrue(calls, "_generate_content_hash must call hashlib.md5")
        for call in calls:
            self.assertTrue(
                _call_has_usedforsecurity_false(call),
                "hashlib.md5 in _generate_content_hash must pass usedforsecurity=False",
            )

    def test_source_literal_usedforsecurity_false(self):
        src = _bot_source()
        self.assertIn("usedforsecurity=False", src)
        self.assertIn("hashlib.md5", src)


class TestContentHashSec001Behavior(unittest.TestCase):
    """Call _generate_content_hash via unbound method (no full bot __init__)."""

    def test_hash_matches_md5_usedforsecurity_false(self):
        bot_mod = _load_bot_module()
        text = "Hello World"
        url = "https://example.com/a"
        image_url = "https://cdn.example.com/img.png"
        content_string = "|".join([text.lower().strip(), url, image_url])
        expected = hashlib.md5(
            content_string.encode("utf-8"), usedforsecurity=False
        ).hexdigest()

        stub = types.SimpleNamespace()
        got = bot_mod.AutonomousBlueskyBotV2._generate_content_hash(
            stub, text, url, image_url
        )
        self.assertEqual(got, expected)
        self.assertEqual(len(got), 32)
        self.assertRegex(got, r"^[0-9a-f]{32}$")

    def test_hash_text_only_stable(self):
        bot_mod = _load_bot_module()
        stub = types.SimpleNamespace()
        a = bot_mod.AutonomousBlueskyBotV2._generate_content_hash(stub, "Same Post")
        b = bot_mod.AutonomousBlueskyBotV2._generate_content_hash(stub, "Same Post")
        self.assertEqual(a, b)
        # lower+strip must not change digest vs explicit lower strip
        c = bot_mod.AutonomousBlueskyBotV2._generate_content_hash(
            stub, "  SAME POST  "
        )
        self.assertEqual(a, c)

    def test_url_and_image_change_hash(self):
        bot_mod = _load_bot_module()
        stub = types.SimpleNamespace()
        base = bot_mod.AutonomousBlueskyBotV2._generate_content_hash(
            stub, "post body"
        )
        with_url = bot_mod.AutonomousBlueskyBotV2._generate_content_hash(
            stub, "post body", url="https://a.example"
        )
        with_img = bot_mod.AutonomousBlueskyBotV2._generate_content_hash(
            stub, "post body", image_url="https://img.example/x.png"
        )
        self.assertNotEqual(base, with_url)
        self.assertNotEqual(base, with_img)
        self.assertNotEqual(with_url, with_img)


def run_sec001_content_hash_assertions() -> None:
    """Callable from verify/acceptance — raises AssertionError on failure."""
    tree = ast.parse(_bot_source(), filename=str(BOT_MODULE_PATH))
    calls = _find_generate_content_hash_md5_calls(tree)
    assert calls, "_generate_content_hash must call hashlib.md5"
    for call in calls:
        assert _call_has_usedforsecurity_false(call), (
            "hashlib.md5 must use usedforsecurity=False"
        )

    bot_mod = _load_bot_module()
    stub = types.SimpleNamespace()
    digest = bot_mod.AutonomousBlueskyBotV2._generate_content_hash(stub, "probe")
    expected = hashlib.md5(
        b"probe", usedforsecurity=False
    ).hexdigest()
    assert digest == expected, f"digest mismatch: {digest!r} != {expected!r}"


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    unittest.main(verbosity=2)
