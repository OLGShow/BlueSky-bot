#!/usr/bin/env python3
"""
QUAL-002: hermetic tests for QualityPipeline + regen exhaustion.

Covers gate (low_signal / semantic_dup), score (low_viral), and
``regenerate_until_quality`` exhaustion → no publish candidate.

Run:
  python -m unittest tests.test_quality_pipeline_qual002 -v
"""

from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from quality_pipeline import (  # noqa: E402
    STAGE_FULL,
    STAGE_GATE,
    STAGE_SCORE,
    QualityContext,
    QualityPipeline,
    regenerate_until_quality,
)


@dataclass
class _FakePost:
    text: str


def _gate_friendly_text() -> str:
    """Enough length + signal markers to pass default QualityGate."""
    return (
        "Study data shows AI adoption grew 42% this year because "
        "teams automated reporting workflows. Key takeaway: measure "
        "outcomes, not hype. What metric matters most for your team? "
        "#AI #productivity"
    )


class _StubAnalyzer:
    """Deterministic viral scores for hermetic score-stage tests."""

    def __init__(self, viral_score: float = 0.8, factors: Optional[List[str]] = None):
        self.viral_score = viral_score
        self.factors = factors or [
            "optimal_length",
            "contains_question",
            "trending_topic",
        ]

    def analyze_post_potential(self, text: str) -> dict:
        return {
            "viral_score": self.viral_score,
            "factors": list(self.factors),
            "recommendations": [],
        }


class TestQualityPipelineStages(unittest.TestCase):
    def test_low_signal_fails_gate_stage(self):
        pipe = QualityPipeline(
            {
                "quality_gate_settings": {
                    "min_signal_density": 0.3,
                    "max_fluff_score": 0.4,
                    "max_semantic_similarity": 0.45,
                }
            },
            analyzer=_StubAnalyzer(),
            require_hashtags=False,
        )
        # Long enough to avoid too_short, but no signal markers
        text = (
            "hello there friends this is just some casual chatter "
            "without numbers facts or questions about anything"
        )
        result = pipe.evaluate(text, QualityContext(recent_posts=[]))
        self.assertFalse(result.ok)
        self.assertEqual(result.stage, STAGE_GATE)
        self.assertTrue(
            (result.reason or "").startswith("low_signal"),
            result.reason,
        )
        self.assertIs(result.gate_ok, False)
        self.assertIsNone(result.score_ok)

    def test_semantic_dup_fails_gate_stage(self):
        pipe = QualityPipeline(
            {
                "quality_gate_settings": {
                    "min_signal_density": 0.1,
                    "max_fluff_score": 0.9,
                    "max_semantic_similarity": 0.3,
                }
            },
            analyzer=_StubAnalyzer(),
            require_hashtags=False,
        )
        text = _gate_friendly_text()
        result = pipe.evaluate(
            text, QualityContext(recent_posts=[text])
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.stage, STAGE_GATE)
        self.assertTrue(
            (result.reason or "").startswith("semantic_dup"),
            result.reason,
        )

    def test_low_viral_fails_score_stage_after_gate(self):
        pipe = QualityPipeline(
            {
                "quality_gate_settings": {"min_signal_density": 0.1},
                "viral_content_settings": {
                    "min_viral_score": 0.9,
                    "required_engagement_triggers": 1,
                },
            },
            analyzer=_StubAnalyzer(viral_score=0.2, factors=["a", "b"]),
            min_combined_score=0.1,
            require_hashtags=False,
        )
        text = _gate_friendly_text()
        result = pipe.evaluate(text, QualityContext(recent_posts=[]))
        self.assertFalse(result.ok)
        self.assertEqual(result.stage, STAGE_SCORE)
        self.assertTrue(result.gate_ok)
        self.assertIs(result.score_ok, False)
        self.assertTrue(
            (result.reason or "").startswith("low_viral"),
            result.reason,
        )

    def test_full_pass_staged_ok(self):
        pipe = QualityPipeline(
            {
                "quality_gate_settings": {"min_signal_density": 0.1},
                "viral_content_settings": {
                    "min_viral_score": 0.3,
                    "required_engagement_triggers": 2,
                },
            },
            analyzer=_StubAnalyzer(viral_score=0.85),
            min_combined_score=0.4,
            require_hashtags=True,
        )
        result = pipe.evaluate(
            _gate_friendly_text(), QualityContext(recent_posts=[])
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.stage, STAGE_FULL)
        self.assertTrue(result.gate_ok)
        self.assertTrue(result.score_ok)


class TestRegenerateUntilQuality(unittest.IsolatedAsyncioTestCase):
    async def test_regen_exhaustion_returns_none(self):
        pipe = QualityPipeline(
            {
                "quality_gate_settings": {
                    "min_signal_density": 0.99,
                    "max_regenerations": 2,
                }
            },
            analyzer=_StubAnalyzer(),
            require_hashtags=False,
        )
        calls = {"n": 0, "regen_modes": []}

        async def always_bad():
            calls["n"] += 1
            return _FakePost(
                "hello there friends chatting casually without any signal"
            )

        def set_mode(on: bool):
            calls["regen_modes"].append(on)

        bad = _FakePost(
            "hello there friends chatting casually without any signal markers"
        )
        post, result = await regenerate_until_quality(
            bad,
            regenerate=always_bad,
            pipeline=pipe,
            recent_posts=[],
            set_regen_mode=set_mode,
        )
        self.assertIsNone(post)
        self.assertFalse(result.ok)
        self.assertEqual(result.stage, STAGE_GATE)
        # initial fail + max_regen regenerations attempted
        self.assertEqual(calls["n"], 2)
        self.assertEqual(calls["regen_modes"], [True, False, True, False])

    async def test_low_signal_triggers_regen_then_pass(self):
        pipe = QualityPipeline(
            {
                "quality_gate_settings": {
                    "min_signal_density": 0.3,
                    "max_regenerations": 2,
                },
                "viral_content_settings": {
                    "min_viral_score": 0.3,
                    "required_engagement_triggers": 2,
                },
            },
            analyzer=_StubAnalyzer(viral_score=0.8),
            min_combined_score=0.4,
            require_hashtags=True,
        )
        calls = {"n": 0}

        async def then_good():
            calls["n"] += 1
            return _FakePost(_gate_friendly_text())

        post, result = await regenerate_until_quality(
            _FakePost("hello friends just chatting with no useful content here"),
            regenerate=then_good,
            pipeline=pipe,
            recent_posts=[],
        )
        self.assertIsNotNone(post)
        self.assertTrue(result.ok)
        self.assertEqual(result.stage, STAGE_FULL)
        self.assertEqual(calls["n"], 1)

    async def test_score_fail_does_not_regen(self):
        pipe = QualityPipeline(
            {
                "quality_gate_settings": {"min_signal_density": 0.1},
                "viral_content_settings": {
                    "min_viral_score": 0.95,
                    "required_engagement_triggers": 1,
                },
            },
            analyzer=_StubAnalyzer(viral_score=0.1, factors=["x", "y"]),
            min_combined_score=0.1,
            require_hashtags=False,
        )
        regen = mock.AsyncMock(return_value=_FakePost(_gate_friendly_text()))
        post, result = await regenerate_until_quality(
            _FakePost(_gate_friendly_text()),
            regenerate=regen,
            pipeline=pipe,
            recent_posts=[],
        )
        self.assertIsNotNone(post)
        self.assertFalse(result.ok)
        self.assertEqual(result.stage, STAGE_SCORE)
        regen.assert_not_called()


class TestScheduledPostUsesPipeline(unittest.TestCase):
    """AST guard: create_scheduled_post calls unified pipeline entry."""

    def test_create_scheduled_post_uses_regenerate_until_quality(self):
        src = (APP_DIR / "bluesky_bot_v2.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("regenerate_until_quality", src)
        self.assertIn("quality_pipeline", src)
        # Dual raw gate.check loop should not remain in create path
        # (method may still reference quality_gate for composition)
        create_idx = src.find("async def create_scheduled_post")
        next_def = src.find("\n    def ", create_idx + 1)
        if next_def < 0:
            next_def = src.find("\n    async def ", create_idx + 1)
        body = src[create_idx:next_def]
        self.assertNotIn("self.quality_gate.check(", body)
        self.assertIn("regenerate_until_quality(", body)


if __name__ == "__main__":
    unittest.main()
