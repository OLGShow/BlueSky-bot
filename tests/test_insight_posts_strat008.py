#!/usr/bin/env python3
"""
STRAT-008: PersonalInsightStrategy + PredictionStrategy — hermetic tests.

No network, atproto, or AutonomousBlueskyBotV2.

Covers:
  - insight happy path (theme → structured → image → post)
  - prediction happy path + powerful model_key
  - empty structured → fallback dict
  - stable STRATEGY_NAME keys
  - strategies package has no bluesky_bot_v2 import (AST)

Run:
  python tests/test_insight_posts_strat008.py
  python -m unittest tests.test_insight_posts_strat008
"""

from __future__ import annotations

import ast
import asyncio
import sys
import unittest
from pathlib import Path
from typing import Any, List, Mapping, Optional
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

STRATEGIES_DIR = APP_DIR / "strategies"
FORBIDDEN = "bluesky_bot_v2"

STRUCTURED = {
    "post_text": "A hard-won personal lesson about the topic.",
    "hashtags": "#insight #lessons",
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


def _make_theme_ports(*, empty_content: bool = False, image_data: Optional[bytes] = b"PNGDATA"):
    from strategies.ports import ImagePostPorts, ThemePostPorts

    posts = FakePosts()
    prompt = FakeImagePrompt()
    gen = FakeImageGen(image_data)
    upload = FakeImageUpload()
    content = FakeContent(empty=empty_content)
    image = ImagePostPorts(
        posts=posts,
        image_prompt=prompt,
        image_gen=gen,
        image_upload=upload,
    )
    ports = ThemePostPorts(content=content, image=image)
    return ports, posts, prompt, gen, upload, content


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


class TestPersonalInsightStrategy(unittest.TestCase):
    def test_stable_strategy_name(self) -> None:
        from strategies.insight_posts import (
            PERSONAL_INSIGHT_STRATEGY_NAME,
            PersonalInsightStrategy,
        )

        self.assertEqual(
            PERSONAL_INSIGHT_STRATEGY_NAME, "_create_personal_insight"
        )
        self.assertEqual(
            PersonalInsightStrategy.STRATEGY_NAME, "_create_personal_insight"
        )

    def test_happy_path_uses_creative_and_image_topic(self) -> None:
        from strategies.insight_posts import PersonalInsightStrategy

        ports, posts, prompt, gen, upload, content = _make_theme_ports()
        strategy = PersonalInsightStrategy(ports)

        with patch(
            "strategies.image_post.random.choice",
            return_value="biggest career mistake",
        ):
            result = asyncio.run(strategy.create())

        self.assertIsInstance(result, FakePost)
        self.assertEqual(result.content_type, "personal_insight")
        self.assertIsNotNone(result.image_blob)
        self.assertEqual(len(content.calls), 1)
        self.assertEqual(content.calls[0][1], "creative")
        self.assertIn("biggest career mistake", content.calls[0][0])
        self.assertEqual(
            prompt.calls, ["personal insight about biggest career mistake"]
        )
        self.assertEqual(upload.calls, [b"PNGDATA"])
        self.assertIn("hard-won personal lesson", result.text)

    def test_empty_structured_uses_fallback(self) -> None:
        from strategies.insight_posts import PersonalInsightStrategy

        ports, posts, prompt, gen, upload, content = _make_theme_ports(
            empty_content=True
        )
        strategy = PersonalInsightStrategy(ports)

        with patch(
            "strategies.image_post.random.choice",
            return_value="overrated trend",
        ):
            result = asyncio.run(strategy.create())

        self.assertIsInstance(result, FakePost)
        self.assertEqual(result.content_type, "personal_insight")
        self.assertIsNone(result.image_blob)
        self.assertIn("overrated trend", result.text)
        self.assertIn("#insight", result.text)
        self.assertEqual(prompt.calls, [])
        self.assertEqual(gen.calls, [])


class TestPredictionStrategy(unittest.TestCase):
    def test_stable_strategy_name(self) -> None:
        from strategies.insight_posts import (
            PREDICTION_STRATEGY_NAME,
            PredictionStrategy,
        )

        self.assertEqual(PREDICTION_STRATEGY_NAME, "_create_prediction_post")
        self.assertEqual(
            PredictionStrategy.STRATEGY_NAME, "_create_prediction_post"
        )

    def test_happy_path_uses_powerful_and_image_topic(self) -> None:
        from strategies.insight_posts import PredictionStrategy

        ports, posts, prompt, gen, upload, content = _make_theme_ports()
        strategy = PredictionStrategy(ports)

        with patch(
            "strategies.image_post.random.choice",
            return_value="AI development in 2025",
        ):
            result = asyncio.run(strategy.create())

        self.assertIsInstance(result, FakePost)
        self.assertEqual(result.content_type, "prediction")
        self.assertIsNotNone(result.image_blob)
        self.assertEqual(len(content.calls), 1)
        self.assertEqual(content.calls[0][1], "powerful")
        self.assertIn("AI development in 2025", content.calls[0][0])
        self.assertEqual(
            prompt.calls,
            ["future prediction about AI development in 2025"],
        )
        self.assertEqual(upload.calls, [b"PNGDATA"])

    def test_empty_structured_uses_fallback(self) -> None:
        from strategies.insight_posts import PredictionStrategy

        ports, posts, prompt, gen, upload, content = _make_theme_ports(
            empty_content=True
        )
        strategy = PredictionStrategy(ports)

        with patch(
            "strategies.image_post.random.choice",
            return_value="crypto market direction",
        ):
            result = asyncio.run(strategy.create())

        self.assertIsInstance(result, FakePost)
        self.assertEqual(result.content_type, "prediction")
        self.assertIsNone(result.image_blob)
        self.assertIn("crypto market direction", result.text)
        self.assertIn("#prediction", result.text)
        self.assertEqual(prompt.calls, [])


class TestPackageExports(unittest.TestCase):
    def test_strategies_exports_insight_family(self) -> None:
        import strategies

        self.assertIn("PersonalInsightStrategy", strategies.__all__)
        self.assertIn("PredictionStrategy", strategies.__all__)
        self.assertIn("PERSONAL_INSIGHT_STRATEGY_NAME", strategies.__all__)
        self.assertIn("PREDICTION_STRATEGY_NAME", strategies.__all__)
        self.assertIs(
            strategies.PersonalInsightStrategy,
            strategies.PersonalInsightStrategy,
        )


if __name__ == "__main__":
    unittest.main()
