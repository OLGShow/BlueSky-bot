#!/usr/bin/env python3
"""Personal insight + prediction strategies — ADR-001 / STRAT-008.

Implements former ``AutonomousBlueskyBotV2._create_personal_insight`` and
``_create_prediction_post`` behind :class:`~post_strategies.PostStrategy`
using :class:`~strategies.ports.ThemePostPorts` /
:class:`~strategies.image_post.ThemePostHelper` only.

Import rules:
- Must not import ``bluesky_bot_v2``.
- Composition root builds ports and registers instances under stable
  ``STRATEGY_NAME`` keys in the hybrid registry.

Out of scope (deferred follow-up): ``_create_viral_hot_take``,
``_create_trending_commentary``.
"""

from __future__ import annotations

from typing import Any, Dict, Sequence

from .image_post import ThemePostHelper
from .ports import ThemePostPorts

# Stable config / learning / A/B / registry keys (do not rename).
PERSONAL_INSIGHT_STRATEGY_NAME = "_create_personal_insight"
PREDICTION_STRATEGY_NAME = "_create_prediction_post"

INSIGHT_AREAS: Sequence[str] = (
    "biggest career mistake",
    "counterintuitive business lesson",
    "overlooked skill for success",
    "industry secret nobody talks about",
    "expensive lesson learned",
    "myth everyone believes",
    "pattern in successful people",
    "red flag in startups",
    "undervalued technology",
    "overrated trend",
)

PREDICTION_AREAS: Sequence[str] = (
    "AI development in 2025",
    "remote work evolution",
    "crypto market direction",
    "tech industry consolidation",
    "programming languages future",
    "startup ecosystem changes",
    "social media platform wars",
    "economic tech impact",
    "cybersecurity threats",
    "developer tools evolution",
)


def _build_insight_prompt(selected_area: str) -> str:
    return f"""
            Create a personal insight post about: "{selected_area}"
            
            Requirements:
            - Share authentic personal experience or observation
            - Include specific example or story
            - Provide actionable takeaway
            - Use vulnerable, honest tone
            - End with relatable question
            - 220-280 characters
            - Feel authentic and human
            
            Format as JSON: {{"post_text": "...", "hashtags": "..."}}
            
            Style: "After [X years/experience], I learned that {selected_area} is... [personal story/insight]. Wish someone told me this earlier. Anyone else experienced this? 💭"
            """


def _build_insight_fallback(selected_area: str) -> Dict[str, str]:
    return {
        "post_text": (
            f"💭 Personal insight: {selected_area} taught me more about "
            "business than any book. Here's what I learned... What's your experience?"
        ),
        "hashtags": "#insight #experience #lessons #personal",
    }


def _build_prediction_prompt(selected_area: str) -> str:
    return f"""
            Create a bold prediction post about: "{selected_area}"
            
            Requirements:
            - Make specific, bold prediction
            - Provide reasoning and evidence
            - Set timeline (6 months, 1 year, 2 years)
            - Include potential consequences
            - Ask for counter-arguments
            - 250-280 characters
            - Use confident, analytical tone
            
            Format as JSON: {{"post_text": "...", "hashtags": "..."}}
            
            Style: "Prediction: By [timeline], {selected_area} will... [specific prediction]. Here's why: [reasoning]. This means [consequences]. Prove me wrong! 🔮"
            """


def _build_prediction_fallback(selected_area: str) -> Dict[str, str]:
    return {
        "post_text": (
            f"🔮 Bold prediction: {selected_area} will surprise everyone "
            "in 2025. Here's my reasoning... What do you think?"
        ),
        "hashtags": "#prediction #future #tech #analysis",
    }


class PersonalInsightStrategy:
    """Theme-list personal insight post via ThemePostHelper + image path.

    Satisfies ``post_strategies.PostStrategy`` structurally (``async create``).
    """

    __slots__ = ("_theme",)

    STRATEGY_NAME = PERSONAL_INSIGHT_STRATEGY_NAME

    def __init__(self, ports: ThemePostPorts) -> None:
        self._theme = ThemePostHelper(ports)

    async def create(self) -> Any:
        """Produce a personal-insight post (image when generation succeeds)."""
        return await self._theme.create(
            INSIGHT_AREAS,
            build_prompt=_build_insight_prompt,
            content_type="personal_insight",
            model_key="creative",
            build_fallback=_build_insight_fallback,
            image_topic=lambda area: f"personal insight about {area}",
        )


class PredictionStrategy:
    """Theme-list prediction post via ThemePostHelper + image path.

    Satisfies ``post_strategies.PostStrategy`` structurally (``async create``).
    """

    __slots__ = ("_theme",)

    STRATEGY_NAME = PREDICTION_STRATEGY_NAME

    def __init__(self, ports: ThemePostPorts) -> None:
        self._theme = ThemePostHelper(ports)

    async def create(self) -> Any:
        """Produce a bold prediction post (image when generation succeeds)."""
        return await self._theme.create(
            PREDICTION_AREAS,
            build_prompt=_build_prediction_prompt,
            content_type="prediction",
            model_key="powerful",
            build_fallback=_build_prediction_fallback,
            image_topic=lambda area: f"future prediction about {area}",
        )
