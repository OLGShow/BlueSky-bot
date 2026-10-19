#!/usr/bin/env python3
"""
STRAT-002: QualityNewsStrategy — hermetic tests with fake NewsStrategyPorts.

No network, atproto, or AutonomousBlueskyBotV2.

Covers:
  - success path (headlines → unique → LLM → link preview)
  - all candidates duplicate → fallback
  - empty headlines → fallback
  - strategies package has no bluesky_bot_v2 import (AST)

Run:
  python tests/test_quality_news_strategy_strat002.py
  python -m unittest tests.test_quality_news_strategy_strat002
"""

from __future__ import annotations

import ast
import asyncio
import sys
import unittest
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

STRATEGIES_DIR = APP_DIR / "strategies"
FORBIDDEN = "bluesky_bot_v2"

SAMPLE_NEWS: Mapping[str, Any] = {
    "title": "OpenAI releases a groundbreaking new model today",
    "description": "A detailed summary of the release and industry impact.",
    "url": "https://example.com/news/openai-model",
    "image_url": "https://example.com/img/openai.jpg",
}


# --- Structural fakes (same shape as STRAT-001) ---


class FakeHeadlines:
    def __init__(self, items: Optional[Sequence[Mapping[str, Any]]] = None):
        self.items = list(items or [])
        self.calls = 0

    async def fetch(self) -> Sequence[Mapping[str, Any]]:
        self.calls += 1
        return self.items


class FakeFeeds:
    def __init__(self, urls: Sequence[str] = ()):
        self._urls = list(urls)

    @property
    def urls(self) -> Sequence[str]:
        return self._urls


class FakeDuplicates:
    def __init__(self, duplicate: bool = False):
        self.duplicate = duplicate
        self.calls: List[tuple] = []

    def is_duplicate(
        self,
        text: str,
        url: Optional[str] = None,
        image_url: Optional[str] = None,
    ) -> bool:
        self.calls.append((text, url, image_url))
        return self.duplicate


class FakeContent:
    def __init__(
        self,
        payload: Optional[Mapping[str, str]] = None,
        *,
        empty: bool = False,
    ):
        self.empty = empty
        self.payload = payload or {
            "post_text": "Interesting turn! 🤔 OpenAI just shipped something big.",
            "hashtags": "#news #AI #technology",
        }
        self.calls: List[tuple] = []

    async def generate(
        self, prompt: str, *, model_key: str = "creative"
    ) -> Optional[Mapping[str, str]]:
        self.calls.append((prompt, model_key))
        if self.empty:
            return None
        return dict(self.payload)


class FakePost:
    """Mutable post shell (``url`` / ``image_url`` assigned on soft preview miss)."""

    def __init__(self, text: str, *, content_type: str = "news") -> None:
        self.text = text
        self.content_type = content_type
        self.url = ""
        self.image_url = ""


class FakePosts:
    def __init__(self) -> None:
        self.calls: List[tuple] = []

    def create_post(self, text: str, *, content_type: str = "news") -> FakePost:
        self.calls.append((text, content_type))
        return FakePost(text, content_type=content_type)


class FakeLinkPreview:
    def __init__(self, result: Optional[Mapping[str, Any]] = None):
        self.result = result if result is not None else {"kind": "preview"}
        self.calls: List[tuple] = []

    async def create_with_preview(
        self,
        text: str,
        url: str,
        title: str,
        description: str,
        image_url: Optional[str] = None,
    ) -> Any:
        self.calls.append((text, url, title, description, image_url))
        return self.result


class FakeFallback:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self) -> dict:
        self.calls += 1
        return {"kind": "fallback"}


def _make_ports(
    *,
    headlines: Optional[Sequence[Mapping[str, Any]]] = None,
    duplicate: bool = False,
    feed_urls: Sequence[str] = ("https://example.com/rss",),
    content_empty: bool = False,
) -> tuple[Any, FakeHeadlines, FakeDuplicates, FakeContent, FakeLinkPreview, FakeFallback, FakePosts]:
    from strategies.ports import NewsStrategyPorts

    h = FakeHeadlines(headlines)
    d = FakeDuplicates(duplicate=duplicate)
    c = FakeContent(empty=content_empty)
    lp = FakeLinkPreview({"kind": "enhanced", "url": SAMPLE_NEWS["url"]})
    fb = FakeFallback()
    posts = FakePosts()
    ports = NewsStrategyPorts(
        headlines=h,
        feeds=FakeFeeds(feed_urls),
        duplicates=d,
        content=c,
        posts=posts,
        link_preview=lp,
        fallback=fb,
    )
    return ports, h, d, c, lp, fb, posts


class TestStrategiesPackageNoBotImport(unittest.TestCase):
    def test_strategies_package_has_no_bluesky_bot_v2_import(self) -> None:
        """AST-only: docstrings may mention the forbidden module name."""
        self.assertTrue(STRATEGIES_DIR.is_dir(), f"missing {STRATEGIES_DIR}")
        py_files = sorted(STRATEGIES_DIR.glob("*.py"))
        self.assertTrue(py_files, "strategies package has no .py files")

        for path in py_files:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(
                            FORBIDDEN,
                            alias.name,
                            f"{path.name} imports {alias.name}",
                        )
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    self.assertNotIn(
                        FORBIDDEN,
                        mod,
                        f"{path.name} imports from {mod}",
                    )


class TestQualityNewsStrategy(unittest.TestCase):
    def test_success_path_returns_link_preview_post(self) -> None:
        from strategies.quality_news import STRATEGY_NAME, QualityNewsStrategy

        self.assertEqual(STRATEGY_NAME, "_create_quality_news_post")

        ports, headlines, duplicates, content, link_preview, fallback, posts = _make_ports(
            headlines=[SAMPLE_NEWS],
        )
        strategy = QualityNewsStrategy(ports)

        with patch(
            "strategies.quality_news.random.choice",
            return_value="Interesting turn! 🤔",
        ):
            result = asyncio.run(strategy.create())

        self.assertEqual(result["kind"], "enhanced")
        self.assertEqual(headlines.calls, 1)
        self.assertEqual(len(duplicates.calls), 1)
        self.assertEqual(duplicates.calls[0][1], SAMPLE_NEWS["url"])
        self.assertEqual(len(content.calls), 1)
        self.assertEqual(content.calls[0][1], "creative")
        self.assertIn(SAMPLE_NEWS["title"], content.calls[0][0])
        self.assertEqual(len(link_preview.calls), 1)
        self.assertEqual(link_preview.calls[0][1], SAMPLE_NEWS["url"])
        self.assertEqual(link_preview.calls[0][4], SAMPLE_NEWS["image_url"])
        self.assertEqual(len(posts.calls), 1)
        self.assertEqual(posts.calls[0][1], "news")
        self.assertEqual(fallback.calls, 0)

    def test_all_duplicates_falls_back(self) -> None:
        from strategies.quality_news import QualityNewsStrategy

        ports, headlines, duplicates, content, link_preview, fallback, posts = _make_ports(
            headlines=[SAMPLE_NEWS],
            duplicate=True,
        )
        strategy = QualityNewsStrategy(ports)

        result = asyncio.run(strategy.create())

        self.assertEqual(result, {"kind": "fallback"})
        self.assertEqual(headlines.calls, 1)
        self.assertEqual(len(duplicates.calls), 1)
        self.assertEqual(content.calls, [])
        self.assertEqual(link_preview.calls, [])
        self.assertEqual(posts.calls, [])
        self.assertEqual(fallback.calls, 1)

    def test_empty_headlines_falls_back(self) -> None:
        from strategies.quality_news import QualityNewsStrategy

        ports, headlines, duplicates, content, link_preview, fallback, posts = _make_ports(
            headlines=[],
            feed_urls=["https://feed.example/a", "https://feed.example/b"],
        )
        strategy = QualityNewsStrategy(ports)

        result = asyncio.run(strategy.create())

        self.assertEqual(result, {"kind": "fallback"})
        self.assertEqual(headlines.calls, 1)
        self.assertEqual(duplicates.calls, [])
        self.assertEqual(content.calls, [])
        self.assertEqual(link_preview.calls, [])
        self.assertEqual(posts.calls, [])
        self.assertEqual(fallback.calls, 1)


if __name__ == "__main__":
    unittest.main()
