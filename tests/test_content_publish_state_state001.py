#!/usr/bin/env python3
"""STATE-001: ContentPublishState hermetic tests."""

from __future__ import annotations

import ast
import sys
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Set

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


@dataclass
class FakeMemory:
    published_content_hashes: Set[str] = field(default_factory=set)
    published_urls: Set[str] = field(default_factory=set)
    successful_posts: List[dict] = field(default_factory=list)
    failed_posts: List[Any] = field(default_factory=list)
    repost_performance: List[Any] = field(default_factory=list)
    viral_posts: List[Any] = field(default_factory=list)
    pattern_blacklist: List[Any] = field(default_factory=list)


class TestContentPublishStateNoBotImport(unittest.TestCase):
    def test_module_acyclic(self) -> None:
        path = APP_DIR / "content_publish_state.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn("bluesky_bot_v2", alias.name)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn("bluesky_bot_v2", node.module or "")


class TestHashAndSimilarity(unittest.TestCase):
    def test_hash_stable(self) -> None:
        from content_publish_state import generate_content_hash

        a = generate_content_hash("Hello World", "https://ex.com", None)
        b = generate_content_hash("hello world", "https://ex.com", None)
        self.assertEqual(a, b)

    def test_jaccard_threshold_fixture(self) -> None:
        from content_publish_state import calculate_text_similarity

        sim = calculate_text_similarity(
            "alpha beta gamma delta",
            "alpha beta gamma epsilon",
        )
        self.assertGreater(sim, 0.5)
        self.assertLess(sim, 1.0)
        near = calculate_text_similarity(
            "same words here again",
            "same words here again #tag",
        )
        self.assertGreater(near, 0.8)


class TestDuplicateAndMark(unittest.TestCase):
    def test_hash_hit(self) -> None:
        from content_publish_state import ContentPublishState, generate_content_hash

        mem = FakeMemory()
        state = ContentPublishState(mem)
        h = generate_content_hash("posted once")
        mem.published_content_hashes.add(h)
        self.assertTrue(state.is_duplicate("posted once"))

    def test_url_hit(self) -> None:
        from content_publish_state import ContentPublishState

        mem = FakeMemory()
        mem.published_urls.add("https://news.example/1")
        state = ContentPublishState(mem)
        self.assertTrue(
            state.is_duplicate("fresh text", url="https://news.example/1")
        )

    def test_similarity_hit(self) -> None:
        from content_publish_state import ContentPublishState

        mem = FakeMemory()
        mem.successful_posts = [
            {
                "text": (
                    "one two three four five six seven eight nine"
                )
            }
        ]
        state = ContentPublishState(mem)
        # 9/10 Jaccard = 0.9 > 0.8
        self.assertTrue(
            state.is_duplicate(
                "one two three four five six seven eight nine ten"
            )
        )

    def test_mark_prunes_past_soft_cap(self) -> None:
        from content_publish_state import ContentPublishState

        mem = FakeMemory()
        state = ContentPublishState(mem)
        for i in range(501):
            state.mark_published(f"post body number {i}", soft_cap=500, keep=400)
        self.assertLessEqual(len(mem.published_content_hashes), 400)

    def test_cleanup_rebuilds_from_recent_posts(self) -> None:
        from content_publish_state import ContentPublishState

        now = datetime(2026, 10, 19, 12, 0, 0)
        mem = FakeMemory()
        mem.published_content_hashes = {"stale"}
        mem.published_urls = {"https://old"}
        mem.successful_posts = [
            {
                "timestamp": (now - timedelta(days=1)).isoformat(),
                "content_hash": "freshhash",
                "url": "https://fresh",
            },
            {
                "timestamp": (now - timedelta(days=40)).isoformat(),
                "content_hash": "oldhash",
                "url": "https://ancient",
            },
        ]
        mem.successful_posts.extend([{"x": i} for i in range(600)])
        state = ContentPublishState(mem)
        state.cleanup_old_hashes(now=now)
        self.assertEqual(mem.published_content_hashes, {"freshhash"})
        self.assertEqual(mem.published_urls, {"https://fresh"})
        self.assertEqual(len(mem.successful_posts), 500)


if __name__ == "__main__":
    unittest.main()
