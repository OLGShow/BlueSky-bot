#!/usr/bin/env python3
"""SOFT-002 / SOFT-003: soft-fail strategies + duplicate fallback — hermetic tests."""

from __future__ import annotations

import ast
import asyncio
import sys
import unittest
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Awaitable
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

STRATEGIES_DIR = APP_DIR / "strategies"
FORBIDDEN = "bluesky_bot_v2"

STRUCTURED = {
    "post_text": "An inspiring soft-fail post body.",
    "hashtags": "#motivation #growth",
}


class FakePost:
    def __init__(
        self,
        text: str,
        *,
        content_type: str = "news",
        url: Optional[str] = None,
        image_url: Optional[str] = None,
        image_blob: Any = None,
    ) -> None:
        self.text = text
        self.content_type = content_type
        self.url = url
        self.image_url = image_url
        self.image_blob = image_blob


class FakePosts:
    def create_post(
        self,
        text: str,
        *,
        content_type: str = "news",
        image_blob: Any = None,
        image_alt_text: Optional[str] = None,
    ) -> FakePost:
        return FakePost(text, content_type=content_type, image_blob=image_blob)


class FakeImagePrompt:
    async def create_prompt(self, text: str) -> str:
        return f"prompt:{text}"


class FakeImageGen:
    def __init__(self, data: Optional[bytes] = b"PNG") -> None:
        self.data = data

    async def generate_image_data(self, prompt: str) -> Optional[bytes]:
        return self.data


class FakeImageUpload:
    async def upload(self, image_data: bytes) -> Optional[Any]:
        return {"cid": "bafy"}


class FakeContent:
    def __init__(self, *, empty: bool = False, model_seen: Optional[List[str]] = None):
        self.empty = empty
        self.model_seen = model_seen if model_seen is not None else []

    async def generate(
        self, prompt: str, *, model_key: str = "creative"
    ) -> Optional[Mapping[str, str]]:
        self.model_seen.append(model_key)
        if self.empty:
            return None
        return dict(STRUCTURED)


def _soft_ports(*, empty: bool = False):
    from strategies.ports import ImagePostPorts, SoftFailPorts

    content = FakeContent(empty=empty)
    image = ImagePostPorts(
        posts=FakePosts(),
        image_prompt=FakeImagePrompt(),
        image_gen=FakeImageGen(),
        image_upload=FakeImageUpload(),
    )
    return SoftFailPorts(content=content, image=image), content


class TestSoftFailNoBotImport(unittest.TestCase):
    def test_soft_fail_module_acyclic(self) -> None:
        path = STRATEGIES_DIR / "soft_fail_posts.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(FORBIDDEN, alias.name)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn(FORBIDDEN, node.module or "")


class TestMotivationalEmergency(unittest.TestCase):
    def test_stable_names(self) -> None:
        from strategies.soft_fail_posts import (
            EMERGENCY_STRATEGY_NAME,
            MOTIVATIONAL_STRATEGY_NAME,
            EmergencyUniqueStrategy,
            MotivationalMomentStrategy,
        )

        self.assertEqual(
            MOTIVATIONAL_STRATEGY_NAME, "_create_motivational_moment_post"
        )
        self.assertEqual(
            EMERGENCY_STRATEGY_NAME, "_create_emergency_unique_post"
        )
        self.assertEqual(
            MotivationalMomentStrategy.STRATEGY_NAME, MOTIVATIONAL_STRATEGY_NAME
        )
        self.assertEqual(
            EmergencyUniqueStrategy.STRATEGY_NAME, EMERGENCY_STRATEGY_NAME
        )

    def test_motivational_happy_path_creative(self) -> None:
        from strategies.soft_fail_posts import MotivationalMomentStrategy

        ports, content = _soft_ports()
        strategy = MotivationalMomentStrategy(ports)
        with patch(
            "strategies.image_post.random.choice",
            return_value="личностный рост",
        ):
            result = asyncio.run(strategy.create())
        self.assertEqual(result.content_type, "motivational")
        self.assertEqual(content.model_seen, ["creative"])
        self.assertIsNotNone(result.image_blob)

    def test_emergency_happy_path_fast(self) -> None:
        from strategies.soft_fail_posts import EmergencyUniqueStrategy

        ports, content = _soft_ports()
        strategy = EmergencyUniqueStrategy(ports)
        with patch(
            "strategies.image_post.random.choice",
            return_value="случайная мысль",
        ):
            result = asyncio.run(strategy.create())
        self.assertEqual(result.content_type, "emergency")
        self.assertEqual(content.model_seen, ["fast"])

    def test_empty_structured_fallback(self) -> None:
        from strategies.soft_fail_posts import MotivationalMomentStrategy

        ports, _ = _soft_ports(empty=True)
        strategy = MotivationalMomentStrategy(ports)
        with patch(
            "strategies.image_post.random.choice",
            return_value="достижение целей",
        ):
            result = asyncio.run(strategy.create())
        self.assertEqual(result.content_type, "motivational")
        self.assertIn("motivates you", result.text.lower())


class TestDuplicateFallbackHelper(unittest.TestCase):
    def test_first_unique_wins(self) -> None:
        from strategies.ports import (
            CallableDuplicateContent,
            CallableFallbackPost,
            CallableStrategyLookup,
            DuplicateFallbackPorts,
        )
        from strategies.soft_fail_posts import DuplicateFallbackHelper

        calls: List[str] = []

        async def opinion() -> FakePost:
            calls.append("opinion")
            return FakePost("unique opinion text")

        async def emergency() -> FakePost:
            calls.append("emergency")
            return FakePost("emergency text")

        def lookup(name: str):
            if name == "_create_personal_opinion_post":
                return opinion
            return None

        helper = DuplicateFallbackHelper(
            DuplicateFallbackPorts(
                lookup=CallableStrategyLookup(lookup),
                duplicates=CallableDuplicateContent(lambda *a, **k: False),
                emergency=CallableFallbackPost(emergency),
            )
        )
        result = asyncio.run(helper.create())
        self.assertEqual(result.text, "unique opinion text")
        self.assertEqual(calls, ["opinion"])

    def test_all_duplicate_uses_emergency(self) -> None:
        from strategies.ports import (
            CallableDuplicateContent,
            CallableFallbackPost,
            CallableStrategyLookup,
            DuplicateFallbackPorts,
        )
        from strategies.soft_fail_posts import (
            DEFAULT_FALLBACK_CHAIN,
            DuplicateFallbackHelper,
        )

        async def maker(label: str) -> FakePost:
            return FakePost(f"dup {label}")

        async def emergency() -> FakePost:
            return FakePost("emergency terminal")

        def lookup(name: str):
            return lambda n=name: maker(n)

        helper = DuplicateFallbackHelper(
            DuplicateFallbackPorts(
                lookup=CallableStrategyLookup(lookup),
                duplicates=CallableDuplicateContent(lambda *a, **k: True),
                emergency=CallableFallbackPost(emergency),
            ),
            chain=DEFAULT_FALLBACK_CHAIN,
        )
        result = asyncio.run(helper.create())
        self.assertEqual(result.text, "emergency terminal")

    def test_resolve_miss_skips(self) -> None:
        from strategies.ports import (
            CallableDuplicateContent,
            CallableFallbackPost,
            CallableStrategyLookup,
            DuplicateFallbackPorts,
        )
        from strategies.soft_fail_posts import DuplicateFallbackHelper

        async def tip() -> FakePost:
            return FakePost("tip unique")

        async def emergency() -> FakePost:
            return FakePost("emergency")

        def lookup(name: str):
            if name == "_create_quality_tip_post":
                return tip
            return None

        helper = DuplicateFallbackHelper(
            DuplicateFallbackPorts(
                lookup=CallableStrategyLookup(lookup),
                duplicates=CallableDuplicateContent(lambda *a, **k: False),
                emergency=CallableFallbackPost(emergency),
            ),
            chain=(
                ("_create_personal_opinion_post", "мнение"),
                ("_create_quality_tip_post", "совет"),
            ),
        )
        result = asyncio.run(helper.create())
        self.assertEqual(result.text, "tip unique")


if __name__ == "__main__":
    unittest.main()
