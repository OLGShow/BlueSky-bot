#!/usr/bin/env python3
"""Viral hot-take + trending commentary strategies — ADR-001 / STRAT-010.

Extracts former ``AutonomousBlueskyBotV2._create_viral_hot_take`` and
``_create_trending_commentary`` behind :class:`~post_strategies.PostStrategy`
using :class:`~strategies.ports.ViralPostsPorts` /
:class:`~strategies.image_post.ImagePostHelper`.

Import rules:
- Must not import ``bluesky_bot_v2``.
- Composition root builds ports and registers instances under stable
  ``STRATEGY_NAME`` keys in the hybrid registry.
"""

from __future__ import annotations

import random
from typing import Any, Dict, Mapping, Optional, Sequence

from .image_post import ImagePostHelper
from .ports import ViralPostsPorts

# Stable config / learning / A/B / registry keys (do not rename).
VIRAL_HOT_TAKE_STRATEGY_NAME = "_create_viral_hot_take"
TRENDING_COMMENTARY_STRATEGY_NAME = "_create_trending_commentary"

HOT_TAKE_TOPICS: Sequence[str] = (
    "AI replacing developers is overhyped",
    "Remote work is killing innovation",
    "Most startups fail because of ego, not market",
    "College degrees are becoming irrelevant in tech",
    "Open source is not sustainable long-term",
    "Crypto is just gambling with extra steps",
    "Social media algorithms are destroying creativity",
    "The metaverse was a $100B mistake",
)

TRENDING_THEMES: Sequence[str] = (
    "latest AI breakthrough",
    "tech layoffs",
    "startup funding news",
    "new programming language",
    "security breach",
    "platform changes",
    "industry controversy",
    "major acquisition",
    "economic changes",
    "regulatory changes in tech",
)


def _build_hot_take_prompt(selected_topic: str) -> str:
    return f"""
            Create a controversial but thoughtful hot take about: "{selected_topic}"
            
            Requirements:
            - Be provocative but not offensive
            - Include surprising statistics or facts
            - Add personal experience or industry insight
            - End with a question to encourage debate
            - Use emotional language strategically
            - 180-250 characters max
            - Include 3-4 relevant hashtags
            
            Format as JSON: {{"post_text": "...", "hashtags": "..."}}
            
            Example style: "Unpopular opinion: {selected_topic}. After 10 years in the industry, I've seen this pattern destroy more companies than market crashes. Here's why... What's your take? 🔥"
            """


def _build_hot_take_fallback(selected_topic: str) -> Dict[str, str]:
    return {
        "post_text": (
            f"🔥 Hot take: {selected_topic}. Change my mind! What's your experience?"
        ),
        "hashtags": "#hottake #controversial #tech #opinion",
    }


def _build_trending_prompt(selected_theme: str) -> str:
    return f"""
            Create ONE concise social post about "{selected_theme}".
            Return ONLY JSON with keys "post_text" and "hashtags".
            post_text: 180-230 chars, concrete angle, one clear implication, one question at the end.
            hashtags: 2-4 English tags starting with #.
            """


def _build_trending_fallback(selected_theme: str) -> Dict[str, str]:
    return {
        "post_text": (
            f"📰 Breaking: {selected_theme} is trending. Here's my take on what "
            "this really means for the industry... Thoughts?"
        ),
        "hashtags": "#breaking #tech #analysis #trends",
    }


class ViralHotTakeStrategy:
    """Controversial hot-take post via ImagePostHelper + viral prompts port.

    Satisfies ``post_strategies.PostStrategy`` structurally (``async create``).
    """

    __slots__ = ("_ports", "_image")

    STRATEGY_NAME = VIRAL_HOT_TAKE_STRATEGY_NAME

    def __init__(self, ports: ViralPostsPorts) -> None:
        self._ports = ports
        self._image = ImagePostHelper(ports.image)

    async def create(self) -> Any:
        """Produce a viral hot-take post (image when generation succeeds)."""
        selected_topic = random.choice(list(HOT_TAKE_TOPICS))

        async def content_creator() -> Optional[Mapping[str, Any]]:
            # Parity with bot: call viral prompts even though the list is unused.
            self._ports.viral_prompts.generate()
            return await self._ports.content.generate(
                _build_hot_take_prompt(selected_topic),
                model_key="powerful",
            )

        async def fallback_creator() -> Dict[str, str]:
            return _build_hot_take_fallback(selected_topic)

        return await self._image.create(
            content_creator,
            f"controversial opinion about {selected_topic}",
            "viral_hot_take",
            fallback_creator,
        )


class TrendingCommentaryStrategy:
    """Trending-theme commentary post via ImagePostHelper.

    Satisfies ``post_strategies.PostStrategy`` structurally (``async create``).
    """

    __slots__ = ("_ports", "_image")

    STRATEGY_NAME = TRENDING_COMMENTARY_STRATEGY_NAME

    def __init__(self, ports: ViralPostsPorts) -> None:
        self._ports = ports
        self._image = ImagePostHelper(ports.image)

    async def create(self) -> Any:
        """Produce a trending commentary post (image when generation succeeds)."""
        selected_theme = random.choice(list(TRENDING_THEMES))

        async def content_creator() -> Optional[Mapping[str, Any]]:
            return await self._ports.content.generate(
                _build_trending_prompt(selected_theme),
                model_key="powerful",
            )

        async def fallback_creator() -> Dict[str, str]:
            return _build_trending_fallback(selected_theme)

        return await self._image.create(
            content_creator,
            f"trending news commentary about {selected_theme}",
            "trending_commentary",
            fallback_creator,
        )
