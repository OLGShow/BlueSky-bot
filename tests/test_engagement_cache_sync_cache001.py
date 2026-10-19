#!/usr/bin/env python3
"""CACHE-001: engagement cache sync hermetic tests."""

from __future__ import annotations

import ast
import sys
import unittest
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Set

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


@dataclass
class FakeMemory:
    commented_posts_cache: Set[str] = field(default_factory=set)
    recent_comments_cache: List[Any] = field(default_factory=list)
    liked_posts_cache: Set[str] = field(default_factory=set)
    reposted_posts_cache: Set[str] = field(default_factory=set)
    followed_users_cache: Set[str] = field(default_factory=set)
    last_update: Any = None


class TestCacheSync(unittest.TestCase):
    def test_acyclic(self) -> None:
        path = APP_DIR / "engagement_cache_sync.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn("bluesky_bot_v2", node.module or "")

    def test_cycle_sync_copies_all(self) -> None:
        from engagement_cache_sync import sync_engagement_caches_to_memory

        mem = FakeMemory()
        now = datetime(2026, 10, 19, 12, 0, 0)
        sync_engagement_caches_to_memory(
            mem,
            commented_posts={"c1"},
            recent_comments=list(range(25)),
            liked_posts={"l1"},
            reposted_posts={"r1"},
            followed_users={"f1"},
            now=now,
        )
        self.assertEqual(mem.commented_posts_cache, {"c1"})
        self.assertEqual(len(mem.recent_comments_cache), 20)
        self.assertEqual(mem.liked_posts_cache, {"l1"})
        self.assertEqual(mem.last_update, now)

    def test_shutdown_skip_missing(self) -> None:
        from engagement_cache_sync import sync_engagement_caches_to_memory

        mem = FakeMemory()
        mem.liked_posts_cache = {"keep"}
        sync_engagement_caches_to_memory(
            mem,
            commented_posts={"c"},
            liked_posts=None,
            skip_missing=True,
        )
        self.assertEqual(mem.commented_posts_cache, {"c"})
        self.assertEqual(mem.liked_posts_cache, {"keep"})

    def test_hydrate(self) -> None:
        from engagement_cache_sync import hydrate_engagement_caches_from_memory

        mem = FakeMemory()
        mem.liked_posts_cache = {"a"}
        mem.recent_comments_cache = ["x"]
        snap = hydrate_engagement_caches_from_memory(mem)
        self.assertEqual(snap["liked_posts"], {"a"})
        self.assertEqual(snap["recent_comments"], ["x"])


if __name__ == "__main__":
    unittest.main()
