#!/usr/bin/env python3
"""
REF-001 / STRAT-006: Theme helper + thin AI-insight / list delegates (AST).

Verifies that `_quality_theme_post` still exists (STRAT-004 ThemePostHelper
bridge) and that quality AI-insight / list methods thin-delegate to extracted
strategies (STRAT-006), without importing or executing the bot.

Run:
  python tests/test_post_strategy_helper_ref001.py
  python -m unittest tests.test_post_strategy_helper_ref001
"""

from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
BOT_MODULE = APP_DIR / "bluesky_bot_v2.py"

HELPER_NAME = "_quality_theme_post"
# (bot method, strategy instance attribute that must expose .create())
THEME_DELEGATES: Tuple[Tuple[str, str], ...] = (
    ("_create_quality_ai_insight", "quality_ai_insight_strategy"),
    ("_create_quality_list_post", "quality_list_strategy"),
)
DISPATCH_STRINGS = (
    "_create_quality_ai_insight",
    "_create_quality_list_post",
)


def _load_module_source() -> str:
    assert BOT_MODULE.is_file(), f"missing bot module: {BOT_MODULE}"
    return BOT_MODULE.read_text(encoding="utf-8", errors="replace")


def _parse_module() -> ast.Module:
    return ast.parse(_load_module_source(), filename=str(BOT_MODULE))


def _find_class(tree: ast.Module, name: str) -> Optional[ast.ClassDef]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def _methods_on_class(cls: ast.ClassDef) -> Dict[str, ast.AsyncFunctionDef | ast.FunctionDef]:
    out: Dict[str, ast.AsyncFunctionDef | ast.FunctionDef] = {}
    for node in cls.body:
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            out[node.name] = node
    return out


def _await_strategy_create_calls(fn: ast.AST, strategy_attr: str) -> List[ast.Call]:
    """Collect ``self.<strategy_attr>.create(...)`` Call nodes."""
    found: List[ast.Call] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "create":
            continue
        value = func.value
        if (
            isinstance(value, ast.Attribute)
            and value.attr == strategy_attr
            and isinstance(value.value, ast.Name)
            and value.value.id == "self"
        ):
            found.append(node)
    return found


def _string_literals_in_module(tree: ast.Module) -> Set[str]:
    literals: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            literals.add(node.value)
    return literals


class TestPostStrategyHelperRef001(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = _load_module_source()
        cls.tree = _parse_module()
        cls.bot_cls = _find_class(cls.tree, "AutonomousBlueskyBotV2")
        if cls.bot_cls is None:
            raise unittest.SkipTest("AutonomousBlueskyBotV2 not found in bluesky_bot_v2.py")
        cls.methods = _methods_on_class(cls.bot_cls)

    def test_quality_theme_post_exists_on_bot(self):
        self.assertIn(
            HELPER_NAME,
            self.methods,
            f"{HELPER_NAME} must be defined on AutonomousBlueskyBotV2",
        )
        helper = self.methods[HELPER_NAME]
        self.assertIsInstance(helper, ast.AsyncFunctionDef)
        arg_names = [a.arg for a in helper.args.args] + [
            a.arg for a in helper.args.kwonlyargs
        ]
        self.assertIn("themes", arg_names)
        for expected in ("build_prompt", "content_type", "model_key", "build_fallback"):
            self.assertIn(expected, arg_names, f"helper missing param {expected!r}")

    def test_theme_methods_thin_delegate_to_strategies(self):
        for method_name, strategy_attr in THEME_DELEGATES:
            with self.subTest(method=method_name):
                self.assertIn(method_name, self.methods, f"{method_name} missing on bot")
                self.assertIn(
                    strategy_attr,
                    self.source,
                    f"{strategy_attr} must be wired on the bot",
                )
                calls = _await_strategy_create_calls(
                    self.methods[method_name], strategy_attr
                )
                self.assertGreaterEqual(
                    len(calls),
                    1,
                    f"{method_name} must call self.{strategy_attr}.create()",
                )

    def test_strategy_dispatch_strings_present(self):
        """Default config / selection still references strategy method names."""
        literals = _string_literals_in_module(self.tree)
        for name in DISPATCH_STRINGS:
            with self.subTest(name=name):
                self.assertIn(name, self.methods, f"{name} method missing")
                self.assertIn(
                    name,
                    self.source,
                    f"{name} must remain in bluesky_bot_v2.py source",
                )
        self.assertIn(
            "_create_quality_ai_insight",
            literals,
            "_create_quality_ai_insight must appear as a string (strategy key)",
        )


def run_ref001_assertions() -> None:
    """Callable from verify_bot.py — raises AssertionError on failure."""
    tree = _parse_module()
    bot_cls = _find_class(tree, "AutonomousBlueskyBotV2")
    assert bot_cls is not None, "AutonomousBlueskyBotV2 not found"
    methods = _methods_on_class(bot_cls)
    assert HELPER_NAME in methods, f"{HELPER_NAME} missing on AutonomousBlueskyBotV2"
    source = _load_module_source()
    for method_name, strategy_attr in THEME_DELEGATES:
        assert method_name in methods, f"{method_name} missing"
        assert strategy_attr in source, f"{strategy_attr} missing from source"
        calls = _await_strategy_create_calls(methods[method_name], strategy_attr)
        assert calls, f"{method_name} must call self.{strategy_attr}.create()"
    for name in DISPATCH_STRINGS:
        assert name in source, f"{name} missing from source"
    literals = _string_literals_in_module(tree)
    assert (
        "_create_quality_ai_insight" in literals
    ), "_create_quality_ai_insight strategy string missing"


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    unittest.main(verbosity=2)
