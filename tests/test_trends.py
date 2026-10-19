#!/usr/bin/env python3
"""Hermetic tests for official Bluesky getTrends pipeline (trends.py)."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Mapping
from unittest.mock import AsyncMock, MagicMock

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


SAMPLE_TRENDS = [
    {
        "topic": "5417c6b9b399",
        "displayName": "Spooky month stream schedules",
        "category": "entertainment",
        "link": "/profile/did:plc:qrz3lhbyuxbeilrc6nekdqme/feed/5417c6b9b399",
        "postCount": 10528,
        "description": "Horror game streams",
    },
    {
        "topic": "aa231c803609",
        "displayName": "Russian strikes hit Kyiv metro station",
        "category": "news",
        "link": "/profile/did:plc:qrz3lhbyuxbeilrc6nekdqme/feed/aa231c803609",
        "postCount": 8000,
        "description": "War news",
    },
    {
        "topic": "3ce43cd39309",
        "displayName": "AI demand may push PS6 price up",
        "category": "tech",
        "link": "/profile/did:plc:qrz3lhbyuxbeilrc6nekdqme/feed/3ce43cd39309",
        "postCount": 4200,
        "description": "Console pricing",
    },
]


class TestNormalizeAndLink(unittest.TestCase):
    def test_feed_uri_from_sidebar_link(self) -> None:
        from trends import feed_uri_from_link

        uri = feed_uri_from_link(
            "/profile/did:plc:qrz3lhbyuxbeilrc6nekdqme/feed/5417c6b9b399"
        )
        self.assertEqual(
            uri,
            "at://did:plc:qrz3lhbyuxbeilrc6nekdqme/app.bsky.feed.generator/5417c6b9b399",
        )

    def test_normalize_trend(self) -> None:
        from trends import normalize_trend

        item = normalize_trend(SAMPLE_TRENDS[0])
        assert item is not None
        self.assertEqual(item.display_name, "Spooky month stream schedules")
        self.assertTrue(item.feed_uri.startswith("at://"))
        self.assertEqual(item.as_legacy_dict()["topic"], item.label)


class TestFilterTrends(unittest.TestCase):
    def test_default_keeps_almost_all(self) -> None:
        from trends import TrendsConfig, filter_trends, normalize_trend

        items = [normalize_trend(r) for r in SAMPLE_TRENDS]
        items = [i for i in items if i]
        cfg = TrendsConfig.from_mapping(
            {"deny_keywords": [], "allow_categories": [], "max_topics": 10}
        )
        out = filter_trends(items, cfg)
        self.assertEqual(len(out), 3)

    def test_optional_deny_keywords_only_on_trends(self) -> None:
        """deny_keywords cuts trends; documented as not applied to RSS."""
        from trends import TrendsConfig, filter_trends, normalize_trend

        items = [normalize_trend(r) for r in SAMPLE_TRENDS]
        items = [i for i in items if i]
        cfg = TrendsConfig.from_mapping(
            {"deny_keywords": ["kyiv", "strikes", "ukraine"], "max_topics": 10}
        )
        out = filter_trends(items, cfg)
        labels = [i.label for i in out]
        self.assertIn("Spooky month stream schedules", labels)
        self.assertIn("AI demand may push PS6 price up", labels)
        self.assertTrue(
            all("kyiv" not in i.label.lower() for i in out)
        )

    def test_trends_config_isolated_from_rss_keys(self) -> None:
        """RSS feeds are not part of TrendsConfig — filter cannot see them."""
        from trends import TrendsConfig

        cfg = TrendsConfig.from_mapping(
            {
                "deny_keywords": ["war"],
                "rss_feeds": ["https://example.com/war.xml"],  # ignored
            }
        )
        self.assertEqual(cfg.deny_keywords, ("war",))
        self.assertFalse(hasattr(cfg, "rss_feeds"))


class TestBlueSkyTrendingTracker(unittest.TestCase):
    def test_http_get_trends_and_cache(self) -> None:
        from trends import BlueSkyTrendingTracker

        calls: List[str] = []

        async def fetch_json(url: str) -> Mapping[str, Any]:
            calls.append(url)
            return {"trends": SAMPLE_TRENDS}

        tracker = BlueSkyTrendingTracker(
            client=None,
            config={"cache_minutes": 45, "deny_keywords": []},
            fetch_json=fetch_json,
        )

        async def _run() -> None:
            first = await tracker.get_filtered_trends()
            second = await tracker.get_filtered_trends()
            self.assertEqual(len(first), 3)
            self.assertEqual(len(calls), 1)  # cache hit
            self.assertEqual(len(second), 3)
            self.assertEqual(tracker.last_source, "http")
            theme = await tracker.pick_theme_for_posts()
            self.assertIsNotNone(theme)

        asyncio.run(_run())

    def test_api_fail_falls_back_to_timeline(self) -> None:
        from trends import BlueSkyTrendingTracker

        record = MagicMock()
        record.text = "Python coding AI startup #python #ai hello world testing"
        post = MagicMock()
        post.post.record = record
        timeline = MagicMock()
        timeline.feed = [post]

        client = MagicMock()
        client.app.bsky.unspecced.get_trends = AsyncMock(
            side_effect=RuntimeError("no unspecced")
        )
        client.app.bsky.feed.get_timeline = AsyncMock(return_value=timeline)

        async def boom(_url: str) -> Dict[str, Any]:
            raise RuntimeError("network down")

        tracker = BlueSkyTrendingTracker(
            client=client,
            config={"deny_keywords": []},
            fetch_json=boom,
        )

        async def _run() -> None:
            topics = await tracker.get_trending_topics(10)
            self.assertEqual(tracker.last_source, "timeline_fallback")
            self.assertTrue(any(t.get("topic") for t in topics))

        asyncio.run(_run())

    def test_use_for_posts_false_returns_none_theme(self) -> None:
        from trends import BlueSkyTrendingTracker

        async def fetch_json(url: str) -> Mapping[str, Any]:
            return {"trends": SAMPLE_TRENDS}

        tracker = BlueSkyTrendingTracker(
            client=None,
            config={"use_for_posts": False},
            fetch_json=fetch_json,
        )

        async def _run() -> None:
            self.assertIsNone(await tracker.pick_theme_for_posts())

        asyncio.run(_run())


class TestTrendingCommentaryLiveTheme(unittest.TestCase):
    def test_live_theme_preferred_over_static(self) -> None:
        import importlib.util

        from strategies.ports import ViralPostsPorts
        from strategies.viral_posts import TrendingCommentaryStrategy

        viral_path = REPO_ROOT / "tests" / "test_viral_strategies_strat010.py"
        spec = importlib.util.spec_from_file_location(
            "viral_strat010_helpers", viral_path
        )
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        ports, _posts, _prompt, _gen, _upload, content, _viral = (
            mod._make_viral_ports(image_data=None)
        )

        async def pick():
            return "AI demand may push PS6 price up"

        ports = ViralPostsPorts(
            content=ports.content,
            image=ports.image,
            viral_prompts=ports.viral_prompts,
            pick_trending_theme=pick,
        )
        strategy = TrendingCommentaryStrategy(ports)
        result = asyncio.run(strategy.create())
        self.assertIn("AI demand may push PS6 price up", content.calls[0][0])
        self.assertEqual(result.content_type, "trending_commentary")


class TestTrendsEngagement(unittest.TestCase):
    def test_likes_from_trend_feed(self) -> None:
        from trends import BlueSkyTrendingTracker
        from trends_engagement import (
            CallableFeedPage,
            CallableRelevance,
            TrendsEngagementConfig,
            TrendsEngagementOrchestrator,
            TrendsEngagementPorts,
        )

        async def fetch_json(url: str) -> Mapping[str, Any]:
            return {"trends": SAMPLE_TRENDS}

        tracker = BlueSkyTrendingTracker(
            client=None,
            config={
                "deny_keywords": [],
                "engagement_topics_per_cycle": 2,
                "engagement_posts_per_topic": 3,
            },
            fetch_json=fetch_json,
        )

        class Rec:
            text = "Interesting AI pricing take for builders"

        class Author:
            did = "did:plc:other"
            handle = "other.bsky.social"

        class Post:
            uri = "at://did:plc:other/app.bsky.feed.post/1"
            cid = "bafytest"
            author = Author()
            record = Rec()
            like_count = 10
            repost_count = 2

        class Entry:
            post = Post()

        async def fetch_feed(feed_uri: str, *, limit: int = 5):
            page = MagicMock()
            page.feed = [Entry()]
            return page

        likes: List[str] = []

        async def like(**kwargs):
            likes.append(kwargs["uri"])
            return True

        ports = TrendsEngagementPorts(
            tracker=tracker,
            feed=CallableFeedPage(fetch_feed),
            relevance=CallableRelevance(lambda text, post: 0.9),
            like=like,
            get_my_did=lambda: "did:plc:me",
            sleep=AsyncMock(),
        )
        orch = TrendsEngagementOrchestrator(ports)
        n = asyncio.run(
            orch.run(TrendsEngagementConfig(like_threshold=0.3, max_likes=2))
        )
        self.assertGreaterEqual(n, 1)
        self.assertTrue(likes)


if __name__ == "__main__":
    unittest.main()
