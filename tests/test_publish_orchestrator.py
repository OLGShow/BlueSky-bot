#!/usr/bin/env python3
"""Hermetic tests for ScheduledPostPublisher (publish extract slice A)."""

from __future__ import annotations

import ast
import asyncio
import sys
import unittest
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, List, Optional
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from publish_orchestrator import ScheduledPostPublisher  # noqa: E402
from publish_ports import PublishPorts  # noqa: E402
from quality_pipeline import QualityResult, STAGE_SCORE  # noqa: E402


@dataclass
class _Safety:
    can_publish: bool = True
    reasons: List[str] = field(default_factory=list)


@dataclass
class _Post:
    text: str = "Hello #ai world with enough signal for quality"
    facets: Any = None
    embed: Any = None
    langs: Any = field(default_factory=lambda: ["en"])
    url: Any = None
    image_url: Any = None
    content_type: str = "general"
    quality_score: float = 0.9
    viral_score: float = 0.5
    viral_factors: List[str] = field(default_factory=list)


@dataclass
class _Created:
    uri: str = "at://did:plc:test/app.bsky.feed.post/abc"


class FakePorts:
    """Minimal PublishPorts stand-in that records calls (no network)."""

    def __init__(
        self,
        *,
        can_publish: bool = True,
        can_spend: bool = True,
        dry_run: bool = True,
        daily_count: int = 0,
        max_posts: int = 10,
        arm_keys: Optional[List[str]] = None,
    ) -> None:
        self.calls: List[str] = []
        self._can_publish = can_publish
        self._can_spend = can_spend
        self._dry_run = dry_run
        self._daily_count = daily_count
        self._max_posts = max_posts
        self._last_date: Optional[date] = date.today()
        self._arm_keys = arm_keys or ["_create_quality_news_post"]
        self._strategy_key = "arm_a"
        self._ab_format = "format_a"
        self._ab_suffix = "suffix"
        self.successful_posts: List[dict] = []
        self.viral_posts: List[dict] = []
        self.dry_run_entries: List[tuple] = []
        self._quality_pipeline = MagicMock()

    def as_ports(self) -> PublishPorts:
        p = self

        async def resolve_strategy(name: str):
            p.calls.append(f"resolve:{name}")
            return _Post()

        async def send_post(post):
            p.calls.append("send_post")
            return _Created()

        async def create_fallback():
            p.calls.append("fallback")
            return None

        async def refresh():
            p.calls.append("refresh_followers")
            return 42

        return PublishPorts(
            safety_status=lambda: _Safety(
                can_publish=p._can_publish,
                reasons=[] if p._can_publish else ["blocked"],
            ),
            can_spend_post=lambda: p._can_spend,
            spend_post=lambda: p.calls.append("spend"),
            get_daily_post_count=lambda: p._daily_count,
            set_daily_post_count=lambda n: setattr(p, "_daily_count", int(n)),
            get_max_posts_per_day=lambda: p._max_posts,
            get_last_post_date=lambda: p._last_date,
            set_last_post_date=lambda d: setattr(p, "_last_date", d),
            get_strategy_arm_keys=lambda: list(p._arm_keys),
            get_successful_posts=lambda: p.successful_posts,
            has_format_bandit=lambda: False,
            pick_format_bandit=lambda arms, recent: "format_a",
            record_format_pick=lambda arm: p.calls.append(f"record_format:{arm}"),
            get_format_bandit_learner=lambda: None,
            pick_ab_format=lambda: p._ab_format,
            get_prompt_suffix=lambda fmt: p._ab_suffix,
            log_pick=lambda **kwargs: p.calls.append(
                f"log_pick:{kwargs.get('action')}:{kwargs.get('arm')}"
            ),
            set_current_ab_format=lambda fmt: setattr(p, "_ab_format", fmt),
            set_current_ab_suffix=lambda s: setattr(p, "_ab_suffix", s),
            get_dry_run_format_label=lambda: "unknown",
            get_trend_timeline_snippets=lambda: [],
            get_trend_rss_headlines=lambda: [],
            get_topic_of_day=lambda texts: None,
            pick_strategy=lambda arms, recent: p._strategy_key,
            record_strategy_pick=lambda key: p.calls.append(f"record_strategy:{key}"),
            get_policy_learner=lambda: None,
            set_current_strategy_key=lambda key: setattr(p, "_strategy_key", key),
            get_current_strategy_key=lambda: p._strategy_key,
            resolve_strategy=resolve_strategy,
            quality_pipeline=p._quality_pipeline,
            set_quality_gate_regen_mode=lambda on: p.calls.append(f"regen_mode:{on}"),
            apply_quality_result=lambda post, result: p.calls.append("apply_quality"),
            is_duplicate=lambda text, url, image_url: False,
            create_fallback=create_fallback,
            evaluate_quality=lambda post: True,
            enforce_text_limit=lambda post: post,
            dry_run=p._dry_run,
            dry_run_log=lambda action, **kwargs: p.dry_run_entries.append(
                (action, kwargs)
            ),
            send_post=send_post,
            mark_published=lambda text, url, image_url: p.calls.append("mark_published"),
            bump_posts_created=lambda: p.calls.append("bump_posts"),
            generate_content_hash=lambda text, url, image_url: "hash",
            append_successful_post=lambda data: p.successful_posts.append(data),
            append_viral_post=lambda data: p.viral_posts.append(data),
            schedule_checks=lambda uri: p.calls.append(f"schedule:{uri}"),
            refresh_followers_at_publish=refresh,
            record_ab_impression=lambda fmt: p.calls.append(f"impression:{fmt}"),
            bump_errors=lambda: p.calls.append("bump_errors"),
        )


class TestPublishOrchestratorNoBotImport(unittest.TestCase):
    def test_modules_have_no_bluesky_bot_v2_import(self) -> None:
        for name in ("publish_orchestrator.py", "publish_ports.py"):
            path = APP_DIR / name
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn("bluesky_bot_v2", alias.name)
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn("bluesky_bot_v2", node.module or "")


class TestScheduledPostPublisherGates(unittest.TestCase):
    def test_safety_block_skips_generation(self) -> None:
        fake = FakePorts(can_publish=False)
        pub = ScheduledPostPublisher(fake.as_ports())
        asyncio.run(pub.run())
        self.assertNotIn("resolve:arm_a", fake.calls)
        self.assertEqual(fake.dry_run_entries, [])

    def test_budget_block_skips_generation(self) -> None:
        fake = FakePorts(can_spend=False)
        pub = ScheduledPostPublisher(fake.as_ports())
        asyncio.run(pub.run())
        self.assertNotIn("resolve:arm_a", fake.calls)
        self.assertEqual(fake.dry_run_entries, [])


class TestScheduledPostPublisherHappyDryRun(unittest.TestCase):
    def test_happy_path_dry_run_no_send(self) -> None:
        import publish_orchestrator as orch_mod

        fake = FakePorts(dry_run=True)
        ports = fake.as_ports()

        async def _fake_regen(post, regenerate, pipeline, recent_posts, set_regen_mode):
            set_regen_mode(True)
            set_regen_mode(False)
            result = QualityResult(
                ok=True,
                stage=STAGE_SCORE,
                reason="ok",
                combined_score=0.9,
                viral_score=0.5,
                factors=[],
            )
            return post, result

        original = orch_mod.regenerate_until_quality
        orch_mod.regenerate_until_quality = _fake_regen
        try:
            pub = ScheduledPostPublisher(ports)
            asyncio.run(pub.run())
        finally:
            orch_mod.regenerate_until_quality = original

        self.assertTrue(
            any(c.startswith("resolve:") for c in fake.calls),
            fake.calls,
        )
        self.assertEqual(len(fake.dry_run_entries), 1)
        self.assertEqual(fake.dry_run_entries[0][0], "send_post")
        self.assertNotIn("send_post", fake.calls)
        self.assertNotIn("spend", fake.calls)
        self.assertNotIn("mark_published", fake.calls)


if __name__ == "__main__":
    unittest.main()
