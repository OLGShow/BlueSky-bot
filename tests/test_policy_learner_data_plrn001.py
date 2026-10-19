#!/usr/bin/env python3
"""
PLRN-001: strategy_key persistence data shape — hermetic unit tests.

No bot / network / Bluesky. Covers weighted_named_entries and
successful_post_bandit_fields (strategy_key + rewarded_checks + null metrics).

Run:
  python -m pytest tests/test_policy_learner_data_plrn001.py -q
  python -m unittest tests.test_policy_learner_data_plrn001
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from post_strategies import (  # noqa: E402
    PostStrategyRegistry,
    StrategyLookupError,
    successful_post_bandit_fields,
)


async def _make_post(label: str = "post") -> str:
    return label


class TestWeightedNamedEntries(unittest.TestCase):
    def test_returns_name_callable_weight_triples(self):
        registry = PostStrategyRegistry()
        registry.register("_create_quality_news_post", _make_post)
        registry.register("_create_personal_opinion_post", _make_post)

        entries = registry.weighted_named_entries(
            {
                "_create_quality_news_post": 0.6,
                "_create_personal_opinion_post": 0.4,
            }
        )
        self.assertEqual(len(entries), 2)
        name0, fn0, w0 = entries[0]
        self.assertEqual(name0, "_create_quality_news_post")
        self.assertEqual(w0, 0.6)
        self.assertEqual(asyncio.run(fn0()), "post")

    def test_skip_missing_true(self):
        registry = PostStrategyRegistry()
        registry.register("keep", _make_post)
        entries = registry.weighted_named_entries(
            {"keep": 0.7, "gone": 0.3},
            skip_missing=True,
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0][0], "keep")

    def test_skip_missing_false_raises(self):
        registry = PostStrategyRegistry()
        registry.register("keep", _make_post)
        with self.assertRaises(StrategyLookupError):
            registry.weighted_named_entries(
                {"keep": 1.0, "gone": 0.5},
                skip_missing=False,
            )

    def test_weighted_entries_delegates_and_drops_names(self):
        registry = PostStrategyRegistry()
        registry.register("a", _make_post)
        registry.register("b", _make_post)
        named = registry.weighted_named_entries({"a": 0.1, "b": 0.2})
        plain = registry.weighted_entries({"a": 0.1, "b": 0.2})
        self.assertEqual([w for _, _, w in named], [w for _, w in plain])
        self.assertEqual(len(plain[0]), 2)


class TestSuccessfulPostBanditFields(unittest.TestCase):
    def test_shape_includes_strategy_key_and_empty_rewarded_checks(self):
        fields = successful_post_bandit_fields("_create_quality_news_post")
        self.assertEqual(fields["strategy_key"], "_create_quality_news_post")
        self.assertEqual(fields["rewarded_checks"], [])
        self.assertIsInstance(fields["rewarded_checks"], list)
        self.assertIsNone(fields["likes"])
        self.assertIsNone(fields["reposts"])
        self.assertIsNone(fields["replies"])

    def test_merges_into_post_data_without_overwriting_core_keys(self):
        strategy_key = "_create_viral_hot_take"
        post_data = {
            "text": "hello",
            "uri": "at://did/app.bsky.feed.post/abc",
            "type": "viral",
            "ab_format": "format_a",
            **successful_post_bandit_fields(strategy_key),
        }
        self.assertEqual(post_data["strategy_key"], strategy_key)
        self.assertEqual(post_data["rewarded_checks"], [])
        self.assertIsNone(post_data["likes"])
        self.assertEqual(post_data["text"], "hello")
        self.assertEqual(post_data["ab_format"], "format_a")


if __name__ == "__main__":
    unittest.main()
