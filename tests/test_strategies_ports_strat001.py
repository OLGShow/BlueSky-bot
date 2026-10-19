#!/usr/bin/env python3
"""
STRAT-001: strategies package + news ports — hermetic smoke tests.

No network, atproto, or AutonomousBlueskyBotV2.

Covers:
  - ``strategies`` / ``strategies.ports`` import cleanly without bluesky_bot_v2
  - Source of ports module has no bluesky_bot_v2 import
  - ``NewsStrategyPorts`` accepts structural fakes for every port field
  - Protocol callables round-trip through the Callable* adapters

Run:
  python tests/test_strategies_ports_strat001.py
  python -m unittest tests.test_strategies_ports_strat001
"""

from __future__ import annotations

import ast
import asyncio
import sys
import unittest
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

PORTS_PATH = APP_DIR / "strategies" / "ports.py"
INIT_PATH = APP_DIR / "strategies" / "__init__.py"
FORBIDDEN = "bluesky_bot_v2"


# --- Import under test (must succeed without bot) ---


class TestStrategiesPackageImport(unittest.TestCase):
    def test_import_strategies_package(self) -> None:
        import strategies  # noqa: F401
        from strategies import NewsStrategyPorts

        self.assertIs(NewsStrategyPorts, strategies.NewsStrategyPorts)
        self.assertIn("NewsStrategyPorts", strategies.__all__)

    def test_import_ports_module(self) -> None:
        from strategies import ports

        self.assertTrue(hasattr(ports, "NewsStrategyPorts"))
        self.assertTrue(hasattr(ports, "RssHeadlinesPort"))
        self.assertTrue(hasattr(ports, "FallbackPostPort"))

    def test_source_has_no_bot_import(self) -> None:
        """AST-only: docstrings may mention the forbidden module name."""
        for path in (PORTS_PATH, INIT_PATH):
            self.assertTrue(path.is_file(), f"missing {path}")
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


# --- Structural fakes ---


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
    async def generate(
        self, prompt: str, *, model_key: str = "creative"
    ) -> Optional[Mapping[str, str]]:
        return {"post_text": "t", "hashtags": "#n", "prompt": prompt, "model": model_key}


class FakePosts:
    def create_post(self, text: str, *, content_type: str = "news") -> dict:
        return {"text": text, "content_type": content_type}


class FakeLinkPreview:
    async def create_with_preview(
        self,
        text: str,
        url: str,
        title: str,
        description: str,
        image_url: Optional[str] = None,
    ) -> dict:
        return {
            "text": text,
            "url": url,
            "title": title,
            "description": description,
            "image_url": image_url,
        }


class FakeFallback:
    async def create(self) -> dict:
        return {"kind": "fallback"}


class TestNewsStrategyPortsBundle(unittest.TestCase):
    def test_bundle_with_fakes(self) -> None:
        from strategies.ports import NewsStrategyPorts

        ports = NewsStrategyPorts(
            headlines=FakeHeadlines([{"title": "Hello world news item", "description": "d"}]),
            feeds=FakeFeeds(["https://example.com/rss"]),
            duplicates=FakeDuplicates(),
            content=FakeContent(),
            posts=FakePosts(),
            link_preview=FakeLinkPreview(),
            fallback=FakeFallback(),
        )

        async def _exercise() -> None:
            items = await ports.headlines.fetch()
            self.assertEqual(len(items), 1)
            self.assertEqual(ports.feeds.urls[0], "https://example.com/rss")
            self.assertFalse(ports.duplicates.is_duplicate("", "https://x", None))
            structured = await ports.content.generate("prompt", model_key="creative")
            self.assertIsNotNone(structured)
            post = ports.posts.create_post("body", content_type="news")
            self.assertEqual(post["content_type"], "news")
            preview = await ports.link_preview.create_with_preview(
                "t", "https://u", "Title", "Desc", "https://img"
            )
            self.assertEqual(preview["url"], "https://u")
            fb = await ports.fallback.create()
            self.assertEqual(fb["kind"], "fallback")

        asyncio.run(_exercise())

    def test_callable_adapters(self) -> None:
        from strategies.ports import (
            CallableDuplicateContent,
            CallableFallbackPost,
            CallableLinkPreview,
            CallablePostFactory,
            CallableRssHeadlines,
            CallableStructuredContent,
            LiveRssFeeds,
            NewsStrategyPorts,
            RssFeedsView,
        )

        async def _fetch():
            return [{"title": "a" * 25, "description": "d"}]

        async def _gen(prompt: str, model_key: str = "creative"):
            return {"post_text": prompt[:10], "hashtags": "#t"}

        async def _preview(text, url, title, description, image_url=None):
            return {"ok": True, "url": url}

        async def _fallback():
            return {"fallback": True}

        feed_box = {"urls": ["https://a/rss", "https://b/rss"]}

        ports = NewsStrategyPorts(
            headlines=CallableRssHeadlines(_fetch),
            feeds=LiveRssFeeds(lambda: feed_box["urls"]),
            duplicates=CallableDuplicateContent(lambda *a, **k: False),
            content=CallableStructuredContent(_gen),
            posts=CallablePostFactory(lambda text, content_type="news": {"text": text}),
            link_preview=CallableLinkPreview(_preview),
            fallback=CallableFallbackPost(_fallback),
        )

        self.assertEqual(len(ports.feeds.urls), 2)
        view = RssFeedsView(urls=("https://static/rss",))
        self.assertEqual(view.urls[0], "https://static/rss")

        async def _run() -> None:
            self.assertEqual(len(await ports.headlines.fetch()), 1)
            self.assertIsNotNone(await ports.content.generate("hello"))
            self.assertTrue((await ports.link_preview.create_with_preview("t", "u", "ti", "d"))["ok"])
            self.assertTrue((await ports.fallback.create())["fallback"])

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
