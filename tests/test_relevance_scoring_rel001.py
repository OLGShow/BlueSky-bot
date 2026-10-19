#!/usr/bin/env python3
"""REL-001: relevance_scoring hermetic tests."""

from __future__ import annotations

import ast
import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def _post(*, likes: int = 0, reposts: int = 0):
    return types.SimpleNamespace(
        post=types.SimpleNamespace(like_count=likes, repost_count=reposts)
    )


class TestRelevanceScoring(unittest.TestCase):
    def test_acyclic(self) -> None:
        path = APP_DIR / "relevance_scoring.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn("bluesky_bot_v2", node.module or "")

    def test_hashtag_and_question_raise_structure(self) -> None:
        from relevance_scoring import calculate_relevance

        settings = {
            "topic_groups": {},
            "hashtag_bonus": 0.08,
            "question_bonus": 0.07,
            "optimal_length_range": [10, 500],
            "length_bonus": 0.05,
            "engagement_max": 0.0,
        }
        plain = calculate_relevance("hello world text here", _post(), settings)
        rich = calculate_relevance(
            "hello world text here? #ai", _post(), settings
        )
        self.assertGreater(rich, plain)

    def test_keyword_group_match(self) -> None:
        from relevance_scoring import calculate_relevance

        settings = {
            "topic_groups": {
                "tech": {"keywords": ["python", "ai"], "weight": 0.2}
            },
            "topical_max": 0.45,
            "hashtag_bonus": 0,
            "question_bonus": 0,
            "optimal_length_range": [1, 10],
            "length_bonus": 0,
            "engagement_max": 0,
        }
        score = calculate_relevance("python and ai rocks", _post(), settings)
        self.assertGreaterEqual(score, 0.2)
        self.assertLessEqual(score, 1.0)


if __name__ == "__main__":
    unittest.main()
