#!/usr/bin/env python3
"""
SEC-001 / TEST-001: content hash uses MD5 with usedforsecurity=False.

After STATE-001 the digest lives in ``content_publish_state.generate_content_hash``;
bot ``_generate_content_hash`` is a thin delegate.

Hermetic: AST source guard + direct function call (no network, no atproto).

Run:
  python tests/test_content_hash_sec001.py
  python -m unittest tests.test_content_hash_sec001
"""

from __future__ import annotations

import ast
import hashlib
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

HASH_MODULE_PATH = APP_DIR / "content_publish_state.py"
BOT_MODULE_PATH = APP_DIR / "bluesky_bot_v2.py"


def _hash_source() -> str:
    assert HASH_MODULE_PATH.is_file(), f"missing {HASH_MODULE_PATH}"
    return HASH_MODULE_PATH.read_text(encoding="utf-8", errors="replace")


def _find_generate_content_hash_md5_calls(tree: ast.AST) -> list[ast.Call]:
    """Return hashlib.md5(...) Call nodes inside generate_content_hash."""
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "generate_content_hash":
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
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
    return False


class TestContentHashSec001Ast(unittest.TestCase):
    """Source/AST guards on content_publish_state — no bot import required."""

    def test_md5_call_has_usedforsecurity_false(self):
        tree = ast.parse(_hash_source(), filename=str(HASH_MODULE_PATH))
        calls = _find_generate_content_hash_md5_calls(tree)
        self.assertTrue(calls, "generate_content_hash must call hashlib.md5")
        for call in calls:
            self.assertTrue(
                _call_has_usedforsecurity_false(call),
                "hashlib.md5 must pass usedforsecurity=False",
            )

    def test_source_literal_usedforsecurity_false(self):
        src = _hash_source()
        self.assertIn("usedforsecurity=False", src)
        self.assertIn("hashlib.md5", src)

    def test_bot_delegates_to_content_publish_state(self):
        bot_src = BOT_MODULE_PATH.read_text(encoding="utf-8", errors="replace")
        self.assertIn("content_publish_state", bot_src)
        self.assertIn(
            "self.content_publish_state.generate_content_hash",
            bot_src,
        )


class TestContentHashSec001Behavior(unittest.TestCase):
    """Call generate_content_hash directly (STATE-001 façade)."""

    def test_hash_matches_md5_usedforsecurity_false(self):
        from content_publish_state import generate_content_hash

        text = "Hello World"
        url = "https://example.com/a"
        image_url = "https://cdn.example.com/img.png"
        content_string = "|".join([text.lower().strip(), url, image_url])
        expected = hashlib.md5(
            content_string.encode("utf-8"), usedforsecurity=False
        ).hexdigest()

        got = generate_content_hash(text, url, image_url)
        self.assertEqual(got, expected)
        self.assertEqual(len(got), 32)
        self.assertRegex(got, r"^[0-9a-f]{32}$")

    def test_hash_text_only_stable(self):
        from content_publish_state import generate_content_hash

        a = generate_content_hash("Same Post")
        b = generate_content_hash("Same Post")
        self.assertEqual(a, b)
        c = generate_content_hash("  SAME POST  ")
        self.assertEqual(a, c)

    def test_url_and_image_change_hash(self):
        from content_publish_state import generate_content_hash

        base = generate_content_hash("post body")
        with_url = generate_content_hash("post body", url="https://a.example")
        with_img = generate_content_hash(
            "post body", image_url="https://img.example/x.png"
        )
        self.assertNotEqual(base, with_url)
        self.assertNotEqual(base, with_img)
        self.assertNotEqual(with_url, with_img)


def run_sec001_content_hash_assertions() -> None:
    """Callable from verify/acceptance — raises AssertionError on failure."""
    tree = ast.parse(_hash_source(), filename=str(HASH_MODULE_PATH))
    calls = _find_generate_content_hash_md5_calls(tree)
    assert calls, "generate_content_hash must call hashlib.md5"
    for call in calls:
        assert _call_has_usedforsecurity_false(call), (
            "hashlib.md5 must use usedforsecurity=False"
        )

    from content_publish_state import generate_content_hash

    digest = generate_content_hash("probe")
    expected = hashlib.md5(b"probe", usedforsecurity=False).hexdigest()
    assert digest == expected, f"digest mismatch: {digest!r} != {expected!r}"


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    unittest.main(verbosity=2)
