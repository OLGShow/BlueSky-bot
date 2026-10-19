#!/usr/bin/env python3
"""RSS-001: rss_content hermetic tests."""

from __future__ import annotations

import ast
import asyncio
import sys
import unittest
from pathlib import Path
from typing import Any, List, Sequence
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


SAMPLE_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>Demo Feed</title>
<item>
  <title>A sufficiently long demo headline for filtering</title>
  <link>https://example.com/a</link>
  <summary>Description that is long enough to matter for scoring purposes here.</summary>
</item>
</channel></rss>
"""


class TestRssHelpers(unittest.TestCase):
    def test_acyclic(self) -> None:
        path = APP_DIR / "rss_content.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn("bluesky_bot_v2", node.module or "")

    def test_clean_html(self) -> None:
        from rss_content import clean_html

        self.assertEqual(clean_html("<b>Hi</b> &amp; you"), "Hi & you")

    def test_dedupe_by_url(self) -> None:
        from rss_content import deduplicate_rss_entries

        entries = [
            {"url": "https://a", "title": "unique alpha title here"},
            {"url": "https://a", "title": "other title words completely"},
            {"url": "https://b", "title": "totally different beta title"},
        ]
        out = deduplicate_rss_entries(entries)
        self.assertEqual(len(out), 2)

    def test_priority_prefers_known_sources(self) -> None:
        from rss_content import calculate_entry_priority

        base = {"title": "x" * 50, "description": "y" * 90, "fetch_time": 1}
        a = calculate_entry_priority(base, "https://techcrunch.com/x")
        b = calculate_entry_priority(base, "https://obscure.example/x")
        self.assertGreater(a, b)


class TestRssFetcher(unittest.TestCase):
    def test_fetch_parses_feed(self) -> None:
        from rss_content import RssContentFetcher, RssContentPorts

        headlines: List[str] = []
        records: List[dict] = []

        async def http_get(url: str, timeout: float = 15):
            return 200, SAMPLE_RSS

        def record_fetch(url, **kwargs):
            records.append({"url": url, **kwargs})

        async def no_sleep(_s: float):
            return None

        ports = RssContentPorts(
            http_get_text=http_get,
            record_fetch=record_fetch,
            set_trend_headlines=lambda t: headlines.extend(t),
            sleep=no_sleep,
        )
        with patch("rss_content.validate_outbound_url", side_effect=lambda u: u):
            result = asyncio.run(
                RssContentFetcher(ports).fetch(
                    ["https://example.com/feed"], max_sources=1
                )
            )
        self.assertEqual(len(result), 1)
        self.assertIn("sufficiently long", result[0]["title"])
        self.assertTrue(headlines)
        self.assertTrue(records)


if __name__ == "__main__":
    unittest.main()
