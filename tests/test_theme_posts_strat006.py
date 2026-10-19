#!/usr/bin/env python3
"""
STRAT-006: QualityAiInsightStrategy + QualityListStrategy — hermetic tests.

No network, atproto, or AutonomousBlueskyBotV2.

Covers:
  - ai_insight happy path (theme → structured → image → post, powerful)
  - list happy path (theme → structured → image → post, creative)
  - empty structured → fallback dict
  - stable STRATEGY_NAME keys
  - strategies package has no bluesky_bot_v2 import (AST)

Run:
  python tests/test_theme_posts_strat006.py
  python -m unittest tests.test_theme_posts_strat006
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
    "post_text": "A thoughtful take on the selected theme.",
    "hashtags": "#ai #theme",
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


def _make_theme_helper(
    *, empty_content: bool = False, image_data: Optional[bytes] = b"PNGDATA"
):
    from strategies.image_post import ThemePostHelper
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
    helper = ThemePostHelper(ThemePostPorts(content=content, image=image))
    return helper, posts, prompt, gen, upload, content


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


class TestQualityAiInsightStrategy(unittest.TestCase):
    def test_stable_strategy_name(self) -> None:
        from strategies.theme_posts import (
            AI_INSIGHT_STRATEGY_NAME,
            QualityAiInsightStrategy,
        )

        self.assertEqual(
            AI_INSIGHT_STRATEGY_NAME, "_create_quality_ai_insight"
        )
        self.assertEqual(
            QualityAiInsightStrategy.STRATEGY_NAME,
            "_create_quality_ai_insight",
        )

    def test_happy_path_uses_powerful_and_theme(self) -> None:
        from strategies.theme_posts import QualityAiInsightStrategy

        helper, posts, prompt, gen, upload, content = _make_theme_helper()
        strategy = QualityAiInsightStrategy(helper)
        theme = "использование AI в повседневной работе"

        with patch(
            "strategies.image_post.random.choice",
            return_value=theme,
        ):
            result = asyncio.run(strategy.create())

        self.assertIsInstance(result, FakePost)
        self.assertEqual(result.content_type, "ai")
        self.assertIsNotNone(result.image_blob)
        self.assertEqual(len(content.calls), 1)
        self.assertEqual(content.calls[0][1], "powerful")
        self.assertIn(theme, content.calls[0][0])
        self.assertEqual(prompt.calls, [theme])
        self.assertEqual(upload.calls, [b"PNGDATA"])
        self.assertIn("thoughtful take", result.text)

    def test_empty_structured_uses_fallback(self) -> None:
        from strategies.theme_posts import QualityAiInsightStrategy

        helper, posts, prompt, gen, upload, content = _make_theme_helper(
            empty_content=True
        )
        strategy = QualityAiInsightStrategy(helper)
        fallback = {
            "post_text": "🤖 AI thoughts (12:00):\n\nArtificial intelligence is reshaping our work.",
            "hashtags": "#AI #future #technology",
        }

        with patch(
            "strategies.image_post.random.choice",
            return_value="эволюция творческих процессов",
        ), patch(
            "strategies.theme_posts.random.choice",
            return_value=fallback,
        ):
            result = asyncio.run(strategy.create())

        self.assertIsInstance(result, FakePost)
        self.assertEqual(result.content_type, "ai")
        self.assertIsNone(result.image_blob)
        self.assertIn("AI thoughts", result.text)
        self.assertIn("#AI", result.text)
        self.assertEqual(prompt.calls, [])
        self.assertEqual(gen.calls, [])


class TestQualityListStrategy(unittest.TestCase):
    def test_stable_strategy_name(self) -> None:
        from strategies.theme_posts import (
            LIST_STRATEGY_NAME,
            QualityListStrategy,
        )

        self.assertEqual(LIST_STRATEGY_NAME, "_create_quality_list_post")
        self.assertEqual(
            QualityListStrategy.STRATEGY_NAME, "_create_quality_list_post"
        )

    def test_happy_path_uses_creative_and_theme(self) -> None:
        from strategies.theme_posts import QualityListStrategy

        helper, posts, prompt, gen, upload, content = _make_theme_helper()
        strategy = QualityListStrategy(helper)
        theme = "полезные инструменты для разработчиков"

        with patch(
            "strategies.image_post.random.choice",
            return_value=theme,
        ):
            result = asyncio.run(strategy.create())

        self.assertIsInstance(result, FakePost)
        self.assertEqual(result.content_type, "list")
        self.assertIsNotNone(result.image_blob)
        self.assertEqual(len(content.calls), 1)
        self.assertEqual(content.calls[0][1], "creative")
        self.assertIn(theme, content.calls[0][0])
        self.assertEqual(prompt.calls, [theme])
        self.assertEqual(upload.calls, [b"PNGDATA"])

    def test_empty_structured_uses_fallback(self) -> None:
        from strategies.theme_posts import QualityListStrategy

        helper, posts, prompt, gen, upload, content = _make_theme_helper(
            empty_content=True
        )
        strategy = QualityListStrategy(helper)
        fallback = {
            "post_text": "📋 Daily developer routine (12:00):\n\n1. Write code",
            "hashtags": "#list #productivity #dev #coding",
        }

        with patch(
            "strategies.image_post.random.choice",
            return_value="тренды в программировании",
        ), patch(
            "strategies.theme_posts.random.choice",
            return_value=fallback,
        ):
            result = asyncio.run(strategy.create())

        self.assertIsInstance(result, FakePost)
        self.assertEqual(result.content_type, "list")
        self.assertIsNone(result.image_blob)
        self.assertIn("Daily developer routine", result.text)
        self.assertIn("#list", result.text)
        self.assertEqual(prompt.calls, [])
        self.assertEqual(gen.calls, [])


class TestPackageExports(unittest.TestCase):
    def test_strategies_exports_theme_family(self) -> None:
        import strategies

        self.assertIn("QualityAiInsightStrategy", strategies.__all__)
        self.assertIn("QualityListStrategy", strategies.__all__)
        self.assertIn("AI_INSIGHT_STRATEGY_NAME", strategies.__all__)
        self.assertIn("LIST_STRATEGY_NAME", strategies.__all__)
        self.assertIs(
            strategies.QualityAiInsightStrategy,
            strategies.QualityAiInsightStrategy,
        )


class TestBotRegistryWiringAst(unittest.TestCase):
    """Hermetic AST: bot overwrites both theme keys with extracted strategies."""

    def test_bot_registers_theme_keys_and_thin_delegates(self) -> None:
        bot_path = APP_DIR / "bluesky_bot_v2.py"
        source = bot_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(bot_path))

        self.assertIn("AI_INSIGHT_STRATEGY_NAME", source)
        self.assertIn("LIST_STRATEGY_NAME", source)
        self.assertIn("QualityAiInsightStrategy", source)
        self.assertIn("QualityListStrategy", source)
        self.assertIn("quality_ai_insight_strategy", source)
        self.assertIn("quality_list_strategy", source)

        bot_cls = None
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "AutonomousBlueskyBotV2":
                bot_cls = node
                break
        self.assertIsNotNone(bot_cls)

        methods = {
            n.name: n
            for n in bot_cls.body
            if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
        }
        for method_name, attr in (
            ("_create_quality_ai_insight", "quality_ai_insight_strategy"),
            ("_create_quality_list_post", "quality_list_strategy"),
        ):
            with self.subTest(method=method_name):
                self.assertIn(method_name, methods)
                found_create = False
                for node in ast.walk(methods[method_name]):
                    if not isinstance(node, ast.Call):
                        continue
                    func = node.func
                    if (
                        isinstance(func, ast.Attribute)
                        and func.attr == "create"
                        and isinstance(func.value, ast.Attribute)
                        and func.value.attr == attr
                    ):
                        found_create = True
                        break
                self.assertTrue(
                    found_create,
                    f"{method_name} must await self.{attr}.create()",
                )


if __name__ == "__main__":
    unittest.main()
