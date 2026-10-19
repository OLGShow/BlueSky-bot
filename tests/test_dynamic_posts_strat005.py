#!/usr/bin/env python3
"""
STRAT-005: Dynamic family strategies — hermetic tests with fakes.

No network, atproto, or AutonomousBlueskyBotV2.

Covers:
  - PersonalOpinionStrategy / QualityTipStrategy / QualityDiscussionStrategy create
  - tip passes request_type ``tip_sharing``
  - discussion picks question_starter / observation
  - hard failure → emergency fallback
  - strategies package has no bluesky_bot_v2 import (AST)
  - stable STRATEGY_NAME keys match learning/config names

Run:
  python tests/test_dynamic_posts_strat005.py
  python -m unittest tests.test_dynamic_posts_strat005
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

DYNAMIC_PAYLOAD = {
    "post_text": "A thoughtful dynamic take on the topic.",
    "hashtags": "#thoughts #community",
    "topic": "growth mindset",
    "content_type": "personal",
}
FALLBACK_PAYLOAD = {
    "post_text": "Fallback dynamic thought.",
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


class FakeDynamic:
    def __init__(
        self,
        payload: Optional[Mapping[str, Any]] = None,
        *,
        raise_on_generate: bool = False,
    ) -> None:
        self.payload = dict(payload or DYNAMIC_PAYLOAD)
        self.raise_on_generate = raise_on_generate
        self.generate_calls: List[Optional[str]] = []
        self.fallback_calls = 0

    async def generate(
        self, content_type: Optional[str] = None
    ) -> Mapping[str, Any]:
        self.generate_calls.append(content_type)
        if self.raise_on_generate:
            raise RuntimeError("dynamic boom")
        return dict(self.payload)

    def fallback(self) -> Mapping[str, Any]:
        self.fallback_calls += 1
        return dict(FALLBACK_PAYLOAD)


class FakeEmergency:
    def __init__(self) -> None:
        self.calls = 0

    async def create(self) -> dict:
        self.calls += 1
        return {"kind": "emergency"}


def _make_ports(
    *,
    raise_on_generate: bool = False,
    image_data: Optional[bytes] = b"PNGDATA",
) -> tuple:
    from strategies.ports import DynamicPostsPorts, ImagePostPorts

    posts = FakePosts()
    image_prompt = FakeImagePrompt()
    image_gen = FakeImageGen(data=image_data)
    image_upload = FakeImageUpload()
    dynamic = FakeDynamic(raise_on_generate=raise_on_generate)
    emergency = FakeEmergency()
    image_ports = ImagePostPorts(
        posts=posts,
        image_prompt=image_prompt,
        image_gen=image_gen,
        image_upload=image_upload,
    )
    ports = DynamicPostsPorts(
        dynamic=dynamic,
        image=image_ports,
        emergency=emergency,
    )
    return ports, dynamic, emergency, posts, image_prompt


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


class TestDynamicPostsStrategies(unittest.TestCase):
    def test_stable_strategy_name_keys(self) -> None:
        from strategies.dynamic_posts import (
            PERSONAL_OPINION_STRATEGY_NAME,
            QUALITY_DISCUSSION_STRATEGY_NAME,
            QUALITY_TIP_STRATEGY_NAME,
        )

        self.assertEqual(
            PERSONAL_OPINION_STRATEGY_NAME, "_create_personal_opinion_post"
        )
        self.assertEqual(QUALITY_TIP_STRATEGY_NAME, "_create_quality_tip_post")
        self.assertEqual(
            QUALITY_DISCUSSION_STRATEGY_NAME, "_create_quality_discussion"
        )

    def test_personal_opinion_happy_path(self) -> None:
        from strategies.dynamic_posts import PersonalOpinionStrategy

        ports, dynamic, emergency, posts, image_prompt = _make_ports()
        strategy = PersonalOpinionStrategy(ports)

        result = asyncio.run(strategy.create())

        self.assertIsInstance(result, FakePost)
        self.assertEqual(dynamic.generate_calls, [None])
        self.assertEqual(image_prompt.calls, ["growth mindset"])
        self.assertEqual(posts.calls[0]["content_type"], "personal")
        self.assertIn("thoughtful dynamic take", posts.calls[0]["text"])
        self.assertEqual(emergency.calls, 0)
        self.assertIsNotNone(posts.calls[0]["image_blob"])

    def test_quality_tip_passes_tip_sharing(self) -> None:
        from strategies.dynamic_posts import QualityTipStrategy

        tip_payload = {
            **DYNAMIC_PAYLOAD,
            "topic": "useful tips",
            "content_type": "tip",
        }
        ports, dynamic, emergency, posts, _prompt = _make_ports()
        dynamic.payload = tip_payload
        strategy = QualityTipStrategy(ports)

        result = asyncio.run(strategy.create())

        self.assertIsInstance(result, FakePost)
        self.assertEqual(dynamic.generate_calls, ["tip_sharing"])
        self.assertEqual(posts.calls[0]["content_type"], "tip")
        self.assertEqual(emergency.calls, 0)

    def test_discussion_picks_observation_when_random_high(self) -> None:
        from strategies.dynamic_posts import QualityDiscussionStrategy

        disc_payload = {
            **DYNAMIC_PAYLOAD,
            "topic": "discussion topic",
            "content_type": "discussion",
        }
        ports, dynamic, emergency, posts, _prompt = _make_ports()
        dynamic.payload = disc_payload
        strategy = QualityDiscussionStrategy(ports)

        with patch("strategies.dynamic_posts.random.random", return_value=0.9):
            result = asyncio.run(strategy.create())

        self.assertIsInstance(result, FakePost)
        self.assertEqual(dynamic.generate_calls, ["observation"])
        self.assertEqual(posts.calls[0]["content_type"], "discussion")
        self.assertEqual(emergency.calls, 0)

    def test_discussion_picks_question_starter_when_random_low(self) -> None:
        from strategies.dynamic_posts import QualityDiscussionStrategy

        ports, dynamic, emergency, posts, _prompt = _make_ports()
        dynamic.payload = {
            **DYNAMIC_PAYLOAD,
            "content_type": "discussion",
        }
        strategy = QualityDiscussionStrategy(ports)

        with patch("strategies.dynamic_posts.random.random", return_value=0.1):
            result = asyncio.run(strategy.create())

        self.assertIsInstance(result, FakePost)
        self.assertEqual(dynamic.generate_calls, ["question_starter"])
        self.assertEqual(emergency.calls, 0)

    def test_hard_failure_uses_emergency(self) -> None:
        from strategies.dynamic_posts import PersonalOpinionStrategy

        ports, dynamic, emergency, posts, _prompt = _make_ports(
            raise_on_generate=True
        )
        strategy = PersonalOpinionStrategy(ports)

        result = asyncio.run(strategy.create())

        self.assertEqual(result, {"kind": "emergency"})
        self.assertEqual(emergency.calls, 1)
        self.assertEqual(posts.calls, [])
        self.assertEqual(len(dynamic.generate_calls), 1)


if __name__ == "__main__":
    unittest.main()
