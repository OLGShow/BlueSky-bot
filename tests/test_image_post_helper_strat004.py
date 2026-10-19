#!/usr/bin/env python3
"""
STRAT-004: ImagePostHelper / ThemePostHelper — hermetic tests with fakes.

No network, atproto, or AutonomousBlueskyBotV2.

Covers:
  - happy path (structured → image → blob → post with image)
  - empty content → fallback dict → text post
  - image miss → text-only post
  - strategies package has no bluesky_bot_v2 import (AST)
  - ThemePostHelper delegates into ImagePostHelper

Run:
  python tests/test_image_post_helper_strat004.py
  python -m unittest tests.test_image_post_helper_strat004
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
    "post_text": "A thoughtful take on the theme.",
    "hashtags": "#ai #theme",
}
FALLBACK = {
    "post_text": "Fallback thought of the day.",
    "hashtags": "#fallback",
}


# --- Structural fakes ---


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


def _make_image_ports(
    *,
    image_data: Optional[bytes] = b"PNGDATA",
    blob: Any = {"cid": "bafyfake"},
):
    from strategies.ports import ImagePostPorts

    posts = FakePosts()
    prompt = FakeImagePrompt()
    gen = FakeImageGen(image_data)
    upload = FakeImageUpload(blob)
    ports = ImagePostPorts(
        posts=posts,
        image_prompt=prompt,
        image_gen=gen,
        image_upload=upload,
    )
    return ports, posts, prompt, gen, upload


class TestStrategiesPackageNoBotImport(unittest.TestCase):
    def test_strategies_package_has_no_bluesky_bot_v2_import(self) -> None:
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


class TestImagePostHelper(unittest.TestCase):
    def test_happy_path_returns_post_with_image(self) -> None:
        from strategies.image_post import ImagePostHelper

        ports, posts, prompt, gen, upload = _make_image_ports()
        helper = ImagePostHelper(ports)

        async def content_creator():
            return dict(STRUCTURED)

        result = asyncio.run(
            helper.create(content_creator, "AI theme", "ai_insight")
        )

        self.assertIsInstance(result, FakePost)
        self.assertEqual(result.content_type, "ai_insight")
        self.assertEqual(result.image_blob, {"cid": "bafyfake"})
        self.assertIsNotNone(result.image_alt_text)
        self.assertIn("A thoughtful take", result.text)
        self.assertEqual(prompt.calls, ["AI theme"])
        self.assertEqual(gen.calls, ["digital art prompt"])
        self.assertEqual(upload.calls, [b"PNGDATA"])
        self.assertEqual(len(posts.calls), 1)
        self.assertIsNotNone(posts.calls[0]["image_blob"])

    def test_empty_content_uses_fallback_dict(self) -> None:
        from strategies.image_post import ImagePostHelper

        ports, posts, prompt, gen, upload = _make_image_ports()
        helper = ImagePostHelper(ports)

        async def content_creator():
            return None

        async def fallback_creator():
            return dict(FALLBACK)

        result = asyncio.run(
            helper.create(
                content_creator,
                "unused topic",
                "opinion",
                fallback_creator,
            )
        )

        self.assertIsInstance(result, FakePost)
        self.assertEqual(result.content_type, "opinion")
        self.assertIsNone(result.image_blob)
        self.assertIn("Fallback thought", result.text)
        self.assertEqual(prompt.calls, [])
        self.assertEqual(gen.calls, [])
        self.assertEqual(upload.calls, [])
        self.assertEqual(len(posts.calls), 1)

    def test_image_miss_returns_text_only(self) -> None:
        from strategies.image_post import ImagePostHelper

        ports, posts, prompt, gen, upload = _make_image_ports(image_data=None)
        helper = ImagePostHelper(ports)

        async def content_creator():
            return dict(STRUCTURED)

        result = asyncio.run(
            helper.create(content_creator, "quiet theme", "tip")
        )

        self.assertIsInstance(result, FakePost)
        self.assertEqual(result.content_type, "tip")
        self.assertIsNone(result.image_blob)
        self.assertIn("A thoughtful take", result.text)
        self.assertEqual(prompt.calls, ["quiet theme"])
        self.assertEqual(gen.calls, ["digital art prompt"])
        self.assertEqual(upload.calls, [])
        self.assertEqual(len(posts.calls), 1)
        self.assertIsNone(posts.calls[0]["image_blob"])


class TestThemePostHelper(unittest.TestCase):
    def test_theme_happy_path_uses_structured_and_image(self) -> None:
        from strategies.image_post import ThemePostHelper
        from strategies.ports import ThemePostPorts

        image_ports, posts, prompt, gen, upload = _make_image_ports()
        content = FakeContent()
        helper = ThemePostHelper(
            ThemePostPorts(content=content, image=image_ports)
        )

        def build_prompt(theme: str) -> str:
            return f"Write about {theme}"

        def build_fallback(theme: str) -> dict:
            return {"post_text": f"fb {theme}", "hashtags": "#fb"}

        with patch(
            "strategies.image_post.random.choice",
            return_value="daily AI habits",
        ):
            result = asyncio.run(
                helper.create(
                    ["daily AI habits", "other"],
                    build_prompt=build_prompt,
                    content_type="ai_insight",
                    model_key="powerful",
                    build_fallback=build_fallback,
                )
            )

        self.assertIsInstance(result, FakePost)
        self.assertEqual(result.content_type, "ai_insight")
        self.assertIsNotNone(result.image_blob)
        self.assertEqual(len(content.calls), 1)
        self.assertEqual(content.calls[0][1], "powerful")
        self.assertIn("daily AI habits", content.calls[0][0])
        self.assertEqual(prompt.calls, ["daily AI habits"])
        self.assertEqual(upload.calls, [b"PNGDATA"])

    def test_theme_empty_structured_uses_fallback(self) -> None:
        from strategies.image_post import ThemePostHelper
        from strategies.ports import ThemePostPorts

        image_ports, posts, prompt, gen, upload = _make_image_ports()
        content = FakeContent(empty=True)
        helper = ThemePostHelper(
            ThemePostPorts(content=content, image=image_ports)
        )

        with patch(
            "strategies.image_post.random.choice",
            return_value="list theme",
        ):
            result = asyncio.run(
                helper.create(
                    ["list theme"],
                    build_prompt=lambda t: f"prompt {t}",
                    content_type="list",
                    model_key="creative",
                    build_fallback=lambda t: {
                        "post_text": f"list fallback: {t}",
                        "hashtags": "#list",
                    },
                )
            )

        self.assertIsInstance(result, FakePost)
        self.assertEqual(result.content_type, "list")
        self.assertIsNone(result.image_blob)
        self.assertIn("list fallback: list theme", result.text)
        self.assertEqual(prompt.calls, [])
        self.assertEqual(gen.calls, [])


class TestPackageExports(unittest.TestCase):
    def test_strategies_exports_image_helpers(self) -> None:
        import strategies

        self.assertIn("ImagePostHelper", strategies.__all__)
        self.assertIn("ThemePostHelper", strategies.__all__)
        self.assertIn("ImagePostPorts", strategies.__all__)
        self.assertIn("ThemePostPorts", strategies.__all__)
        self.assertIs(strategies.ImagePostHelper, strategies.ImagePostHelper)


if __name__ == "__main__":
    unittest.main()
