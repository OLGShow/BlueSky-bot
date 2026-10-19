#!/usr/bin/env python3
"""LEARN-001: strategy weight updates from topic outcomes — hermetic tests."""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


class TestStrategyLearningNoBotImport(unittest.TestCase):
    def test_module_has_no_bluesky_bot_v2_import(self) -> None:
        path = APP_DIR / "strategy_learning.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn("bluesky_bot_v2", alias.name)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn("bluesky_bot_v2", node.module or "")


class TestComputeUpdatedStrategyWeights(unittest.TestCase):
    def test_empty_outcomes_noop(self) -> None:
        from strategy_learning import compute_updated_strategy_weights

        weights = {"_create_viral_hot_take": 0.2}
        updated, changed = compute_updated_strategy_weights({}, weights)
        self.assertFalse(changed)
        self.assertEqual(updated, weights)

    def test_above_avg_increases_weight(self) -> None:
        from strategy_learning import compute_updated_strategy_weights

        outcomes = {
            "viral hot take": {"total_er": 20.0, "count": 1},
            "other topic": {"total_er": 2.0, "count": 1},
        }
        weights = {
            "_create_viral_hot_take": 0.20,
            "_create_quality_tip_post": 0.20,
        }
        updated, changed = compute_updated_strategy_weights(outcomes, weights)
        self.assertTrue(changed)
        self.assertGreater(updated["_create_viral_hot_take"], 0.20)

    def test_below_avg_decreases_weight(self) -> None:
        from strategy_learning import compute_updated_strategy_weights

        outcomes = {
            "viral hot take": {"total_er": 1.0, "count": 1},
            "tip": {"total_er": 20.0, "count": 1},
        }
        weights = {"_create_viral_hot_take": 0.20}
        updated, changed = compute_updated_strategy_weights(outcomes, weights)
        self.assertTrue(changed)
        self.assertLess(updated["_create_viral_hot_take"], 0.20)

    def test_clamp_bounds(self) -> None:
        from strategy_learning import (
            WEIGHT_MAX,
            WEIGHT_MIN,
            compute_updated_strategy_weights,
        )

        outcomes = {
            "viral hot take": {"total_er": 100.0, "count": 1},
            "other": {"total_er": 1.0, "count": 1},
        }
        weights = {"_create_viral_hot_take": 0.48}
        updated, _ = compute_updated_strategy_weights(outcomes, weights)
        self.assertLessEqual(updated["_create_viral_hot_take"], WEIGHT_MAX)

        outcomes_low = {
            "viral hot take": {"total_er": 1.0, "count": 1},
            "other": {"total_er": 100.0, "count": 1},
        }
        weights_low = {"_create_viral_hot_take": 0.06}
        updated_low, _ = compute_updated_strategy_weights(
            outcomes_low, weights_low
        )
        self.assertGreaterEqual(
            updated_low["_create_viral_hot_take"], WEIGHT_MIN
        )

    def test_apply_function_removed(self) -> None:
        """PLRN-007: apply_* dual-writer deleted; compute helpers remain."""
        import strategy_learning as sl

        self.assertFalse(hasattr(sl, "apply_strategy_weights_from_outcomes"))
        self.assertTrue(hasattr(sl, "compute_updated_strategy_weights"))
        self.assertEqual(sl.WEIGHT_MIN, 0.05)


if __name__ == "__main__":
    unittest.main()
