#!/usr/bin/env python3
"""
STRAT-010: ViralHotTakeStrategy + TrendingCommentaryStrategy — hermetic tests.

No network, atproto, or AutonomousBlueskyBotV2.
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

STRUCTURED = {
    "post_text": "A provocative but thoughtful hot take.",
    "hashtags": "#hottake #tech",
}


class FakePost:
    def __init__(
        self,
        text: str,
        *,
        content_type: str = "news",
        image_blob: Any = None,
        image_alt_text: Optional[str] = None,
    ) -> None:
        self.text = text
        self.content_type = content_type
        self.image_blob = image_blob
        self.image_alt_text = image_alt_text


class FakePosts:
    def __init__(self) -> None:
        self.calls: List[dict] = []

    def create_post(
        self,
        text: str,
        *,
        content_type: str = "news",
        image_blob: Any = None,
        image_alt_text: Optional[str] = None,
    ) -> FakePost:
        self.calls.append(
            {
                "text": text,
                "content_type": content_type,
                "image_blob": image_blob,
                "image_alt_text": image_alt_text,
            }
        )
        return FakePost(
            text,
            content_type=content_type,
            image_blob=image_blob,
            image_alt_text=image_alt_text,
        )


class FakeImagePrompt:
    def __init__(self, prompt: str = "digital art prompt") -> None:
        self.prompt = prompt
        self.calls: List[str] = []

    async def create_prompt(self, text: str) -> str:
        self.calls.append(text)
        return self.prompt


class FakeImageGen:
    def __init__(self, data: Optional[bytes] = b"PNGDATA") -> None:
        self.data = data
        self.calls: List[str] = []

    async def generate_image_data(self, prompt: str) -> Optional[bytes]:
        self.calls.append(prompt)
        return self.data


class FakeImageUpload:
    def __init__(self, blob: Any = {"cid": "bafyfake"}) -> None:
        self.blob = blob
        self.calls: List[bytes] = []

    async def upload(self, image_data: bytes) -> Optional[Any]:
        self.calls.append(image_data)
        return self.blob


class FakeContent:
    def __init__(
        self,
        payload: Optional[Mapping[str, str]] = None,
        *,
        empty: bool = False,
    ) -> None:
        self.empty = empty
        self.payload = payload or dict(STRUCTURED)
        self.calls: List[tuple] = []

    async def generate(
        self, prompt: str, *, model_key: str = "creative"
    ) -> Optional[Mapping[str, str]]:
        self.calls.append((prompt, model_key))
        if self.empty:
            return None
        return dict(self.payload)


class FakeViralPrompts:
    def __init__(self, prompts: Optional[Sequence[str]] = None) -> None:
        self.prompts = list(prompts or ["viral template"])
        self.calls = 0

    def generate(self) -> Sequence[str]:
        self.calls += 1
        return list(self.prompts)


def _make_viral_ports(
    *, empty_content: bool = False, image_data: Optional[bytes] = b"PNGDATA"
):
    from strategies.ports import ImagePostPorts, ViralPostsPorts

    posts = FakePosts()
    prompt = FakeImagePrompt()
    gen = FakeImageGen(image_data)
    upload = FakeImageUpload()
    content = FakeContent(empty=empty_content)
    viral = FakeViralPrompts()
    image = ImagePostPorts(
        posts=posts,
        image_prompt=prompt,
        image_gen=gen,
        image_upload=upload,
    )
    ports = ViralPostsPorts(content=content, image=image, viral_prompts=viral)
    return ports, posts, prompt, gen, upload, content, viral


class TestViralPackageNoBotImport(unittest.TestCase):
    def test_viral_posts_has_no_bluesky_bot_v2_import(self) -> None:
        path = STRATEGIES_DIR / "viral_posts.py"
        self.assertTrue(path.is_file(), f"missing {path}")
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(FORBIDDEN, alias.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                self.assertNotIn(FORBIDDEN, mod)


class TestViralHotTakeStrategy(unittest.TestCase):
    def test_stable_strategy_name(self) -> None:
        from strategies.viral_posts import (
            VIRAL_HOT_TAKE_STRATEGY_NAME,
            ViralHotTakeStrategy,
        )

        self.assertEqual(VIRAL_HOT_TAKE_STRATEGY_NAME, "_create_viral_hot_take")
        self.assertEqual(
            ViralHotTakeStrategy.STRATEGY_NAME, "_create_viral_hot_take"
        )

    def test_happy_path_calls_viral_prompts_and_powerful(self) -> None:
        from strategies.viral_posts import ViralHotTakeStrategy

        ports, posts, prompt, gen, upload, content, viral = _make_viral_ports()
        strategy = ViralHotTakeStrategy(ports)

        with patch(
            "strategies.viral_posts.random.choice",
            return_value="Crypto is just gambling with extra steps",
        ):
            result = asyncio.run(strategy.create())

        self.assertIsInstance(result, FakePost)
        self.assertEqual(result.content_type, "viral_hot_take")
        self.assertIsNotNone(result.image_blob)
        self.assertEqual(viral.calls, 1)
        self.assertEqual(content.calls[0][1], "powerful")
        self.assertIn("Crypto is just gambling", content.calls[0][0])
        self.assertIn("controversial opinion about", prompt.calls[0])

    def test_empty_structured_uses_fallback(self) -> None:
        from strategies.viral_posts import ViralHotTakeStrategy

        ports, posts, prompt, gen, upload, content, viral = _make_viral_ports(
            empty_content=True
        )
        strategy = ViralHotTakeStrategy(ports)

        with patch(
            "strategies.viral_posts.random.choice",
            return_value="The metaverse was a $100B mistake",
        ):
            result = asyncio.run(strategy.create())

        self.assertEqual(result.content_type, "viral_hot_take")
        self.assertIsNone(result.image_blob)
        self.assertIn("metaverse", result.text)
        self.assertIn("#hottake", result.text)
        self.assertEqual(viral.calls, 1)
        self.assertEqual(prompt.calls, [])


class TestTrendingCommentaryStrategy(unittest.TestCase):
    def test_stable_strategy_name(self) -> None:
        from strategies.viral_posts import (
            TRENDING_COMMENTARY_STRATEGY_NAME,
            TrendingCommentaryStrategy,
        )

        self.assertEqual(
            TRENDING_COMMENTARY_STRATEGY_NAME, "_create_trending_commentary"
        )
        self.assertEqual(
            TrendingCommentaryStrategy.STRATEGY_NAME,
            "_create_trending_commentary",
        )

    def test_happy_path(self) -> None:
        from strategies.viral_posts import TrendingCommentaryStrategy

        ports, posts, prompt, gen, upload, content, viral = _make_viral_ports()
        strategy = TrendingCommentaryStrategy(ports)

        with patch(
            "strategies.viral_posts.random.choice",
            return_value="tech layoffs",
        ):
            result = asyncio.run(strategy.create())

        self.assertEqual(result.content_type, "trending_commentary")
        self.assertIsNotNone(result.image_blob)
        self.assertEqual(viral.calls, 0)
        self.assertEqual(content.calls[0][1], "powerful")
        self.assertIn("tech layoffs", content.calls[0][0])

    def test_image_miss_text_only(self) -> None:
        from strategies.viral_posts import TrendingCommentaryStrategy

        ports, posts, prompt, gen, upload, content, viral = _make_viral_ports(
            image_data=None
        )
        strategy = TrendingCommentaryStrategy(ports)

        with patch(
            "strategies.viral_posts.random.choice",
            return_value="security breach",
        ):
            result = asyncio.run(strategy.create())

        self.assertEqual(result.content_type, "trending_commentary")
        self.assertIsNone(result.image_blob)
        self.assertEqual(upload.calls, [])


if __name__ == "__main__":
    unittest.main()
