#!/usr/bin/env python3
"""
TEST-001 (registry slice): PostStrategyRegistry — hermetic unit tests.

No bot / network. Covers register / get / missing / weighted_entries.

Run:
  python tests/test_post_strategies_strat.py
  python -m unittest tests.test_post_strategies_strat
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from post_strategies import (  # noqa: E402
    CallablePostStrategy,
    PostStrategyRegistry,
    StrategyLookupError,
    build_bound_registry,
    register_bound_methods,
)


async def _make_post(label: str = "post") -> str:
    return label


class TestPostStrategyRegistry(unittest.TestCase):
    def test_register_and_get(self):
        registry = PostStrategyRegistry()
        registry.register("alpha", _make_post)

        strategy = registry.get("alpha")
        self.assertIsInstance(strategy, CallablePostStrategy)
        self.assertEqual(strategy.name, "alpha")
        self.assertIn("alpha", registry)
        self.assertEqual(len(registry), 1)
        self.assertEqual(registry.list(), ["alpha"])

    def test_get_missing_raises_strategy_lookup_error(self):
        registry = PostStrategyRegistry()
        with self.assertRaises(StrategyLookupError) as ctx:
            registry.get("missing")
        self.assertEqual(str(ctx.exception), "'missing'")

        with self.assertRaises(StrategyLookupError):
            registry.resolve("missing")

    def test_register_rejects_empty_name(self):
        registry = PostStrategyRegistry()
        with self.assertRaises(ValueError):
            registry.register("", _make_post)
        with self.assertRaises(ValueError):
            registry.register(None, _make_post)  # type: ignore[arg-type]

    def test_register_overwrite_false_raises(self):
        registry = PostStrategyRegistry()
        registry.register("dup", _make_post)
        with self.assertRaises(ValueError):
            registry.register("dup", _make_post, overwrite=False)

    def test_resolve_returns_awaitable_callable(self):
        registry = PostStrategyRegistry()

        async def _fn() -> str:
            return "ok"

        registry.register("r1", _fn)
        resolved = registry.resolve("r1")
        self.assertEqual(asyncio.run(resolved()), "ok")

    def test_weighted_entries_skip_missing_true(self):
        registry = PostStrategyRegistry()
        registry.register("keep", _make_post)

        entries = registry.weighted_entries(
            {"keep": 0.7, "gone": 0.3},
            skip_missing=True,
        )
        self.assertEqual(len(entries), 1)
        fn, weight = entries[0]
        self.assertEqual(weight, 0.7)
        self.assertEqual(asyncio.run(fn()), "post")

    def test_weighted_entries_skip_missing_false_raises(self):
        registry = PostStrategyRegistry()
        registry.register("keep", _make_post)

        with self.assertRaises(StrategyLookupError):
            registry.weighted_entries(
                {"keep": 1.0, "gone": 0.5},
                skip_missing=False,
            )

    def test_weighted_entries_preserves_config_order_and_weights(self):
        registry = PostStrategyRegistry()
        registry.register("a", _make_post)
        registry.register("b", _make_post)
        registry.register("c", _make_post)

        weights = {"a": 0.1, "b": 0.2, "c": 0.3}
        entries = registry.weighted_entries(weights)
        self.assertEqual([w for _, w in entries], [0.1, 0.2, 0.3])

    def test_register_bound_methods_and_build_bound_registry(self):
        class Owner:
            async def _create_quality_news_post(self) -> str:
                return "news"

            async def _create_personal_opinion_post(self) -> str:
                return "opinion"

        owner = Owner()
        registry = PostStrategyRegistry()
        registered = register_bound_methods(
            registry,
            owner,
            [
                "_create_quality_news_post",
                "_create_personal_opinion_post",
                "_missing_method",
            ],
        )
        self.assertEqual(
            registered,
            ["_create_quality_news_post", "_create_personal_opinion_post"],
        )
        self.assertEqual(len(registry), 2)

        reg2, ok, missing = build_bound_registry(
            owner,
            [
                "_create_quality_news_post",
                "_nope",
            ],
        )
        self.assertEqual(ok, ["_create_quality_news_post"])
        self.assertEqual(missing, ["_nope"])
        self.assertIn("_create_quality_news_post", reg2)


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    unittest.main(verbosity=2)
