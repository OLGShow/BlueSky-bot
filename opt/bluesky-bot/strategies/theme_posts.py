#!/usr/bin/env python3
"""Theme-family post strategies — ADR-001 / STRAT-006.

Extracts former ``AutonomousBlueskyBotV2._create_quality_ai_insight`` and
``_create_quality_list_post`` behind :class:`~post_strategies.PostStrategy`
using :class:`~strategies.image_post.ThemePostHelper` (STRAT-004).

Import rules:
- Must not import ``bluesky_bot_v2``.
- Composition root builds ``ThemePostHelper`` / ports and registers instances
  under stable config keys in the hybrid registry.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime
from typing import Any, Dict, Sequence

from .image_post import ThemePostHelper

logger = logging.getLogger(__name__)

# Stable config / learning / A/B / registry keys (do not rename).
AI_INSIGHT_STRATEGY_NAME = "_create_quality_ai_insight"
LIST_STRATEGY_NAME = "_create_quality_list_post"

AI_ASPECTS: Sequence[str] = (
    "использование AI в повседневной работе",
    "изменения в подходах к программированию",
    "взаимодействие человека и машины",
    "эволюция творческих процессов",
    "влияние на профессиональные навыки",
)

LIST_THEMES: Sequence[str] = (
    "полезные инструменты для разработчиков",
    "тренды в программировании",
    "книги для IT-специалистов",
    "лайфхаки продуктивности",
    "ресурсы для изучения технологий",
    "ошибки начинающих программистов",
    "принципы хорошего кода",
    "навыки для карьерного роста",
    "языки программирования для изучения",
    "инструменты командной работы",
)


def _build_ai_insight_prompt(selected_aspect: str) -> str:
    return f"""
            Create a thoughtful social media post about "{selected_aspect}".
            Provide the output in JSON format with two keys: "post_text" (in English, 180-220 characters, personal and engaging - can end with a question, statement, observation, or emoji) and "hashtags" (in English, 3-4 relevant tags, starting with #).

            Examples:
            {{
              "post_text": "AI assistants are changing how I approach coding. I'm definitely becoming more efficient, not sure about creativity yet 🤔",
              "hashtags": "#AI #coding #futureofwork #thoughts"
            }}
            {{
              "post_text": "Been using AI for brainstorming lately. It's like having a tireless creative partner that never judges your weird ideas ✨",
              "hashtags": "#AI #creativity #productivity #tools"
            }}
            {{
              "post_text": "The human-AI collaboration feels so natural now. We're not replacing humans, we're augmenting them. That's the real revolution.",
              "hashtags": "#AI #future #collaboration #tech"
            }}
            """


def _build_ai_insight_fallback(_selected_aspect: str) -> Dict[str, str]:
    current_time = datetime.now().strftime("%H:%M")
    fallback_options = [
        {
            "post_text": (
                f"🤖 AI thoughts ({current_time}):\n\n"
                "Artificial intelligence is reshaping our work. "
                "The possibilities are endless! ✨"
            ),
            "hashtags": "#AI #future #technology",
        },
        {
            "post_text": (
                f"💭 Tech reflection ({current_time}):\n\n"
                "Every tool we use shapes how we think. AI is no exception."
            ),
            "hashtags": "#AI #productivity #mindset",
        },
        {
            "post_text": (
                f"🔬 Daily observation ({current_time}):\n\n"
                "Watching AI evolve is like witnessing the birth of a new species."
            ),
            "hashtags": "#AI #evolution #technology",
        },
    ]
    return random.choice(fallback_options)


def _build_list_prompt(selected_theme: str) -> str:
    return f"""
            Create a social media post based on the list idea: "{selected_theme}".
            Provide the output in JSON format. The "post_text" (in English, max 280 chars) should have a title, a short numbered list, and a natural ending (statement, emoji, question, or observation). The "hashtags" (in English) should be 3-4 relevant tags.

            Examples for "useful dev tools":
            {{
              "post_text": "🔥 TOP-3 tools for code\\n\\n1️⃣ VS Code - best editor\\n2️⃣ Git - version control\\n3️⃣ Postman - API testing\\n\\nGame changers for productivity! 🚀",
              "hashtags": "#tools #development #useful #coding"
            }}
            {{
              "post_text": "📚 Must-read books for developers:\\n\\n1️⃣ Clean Code\\n2️⃣ Design Patterns\\n3️⃣ Pragmatic Programmer\\n\\nClassics never get old ✨",
              "hashtags": "#books #learning #development #career"
            }}
            """


def _build_list_fallback(_selected_theme: str) -> Dict[str, str]:
    current_time = datetime.now().strftime("%H:%M")
    fallback_options = [
        {
            "post_text": (
                f"📋 Daily developer routine ({current_time}):\n\n"
                "1. Write code\n2. Drink coffee\n3. Debug\n4. Repeat\n\n"
                "The eternal cycle! ☕"
            ),
            "hashtags": "#list #productivity #dev #coding",
        },
        {
            "post_text": (
                f"🔧 Essential tools ({current_time}):\n\n"
                "1. Good IDE\n2. Version control\n3. Stack Overflow\n\n"
                "Basics that never fail 💪"
            ),
            "hashtags": "#tools #development #basics #tech",
        },
        {
            "post_text": (
                f"💡 Simple truths ({current_time}):\n\n"
                "1. Code works mysteriously\n2. Bugs appear from nowhere\n"
                "3. Coffee fixes everything\n\nSoftware development reality 😅"
            ),
            "hashtags": "#humor #coding #life #truth",
        },
    ]
    return random.choice(fallback_options)


class QualityAiInsightStrategy:
    """AI insight theme strategy via :class:`ThemePostHelper`.

    Satisfies ``post_strategies.PostStrategy`` structurally (``async create``).
    """

    __slots__ = ("_theme",)

    STRATEGY_NAME = AI_INSIGHT_STRATEGY_NAME

    def __init__(self, theme_helper: ThemePostHelper) -> None:
        self._theme = theme_helper

    async def create(self) -> Any:
        """Produce an AI-insight post (theme → structured → image/fallback)."""
        logger.info("🧠 Theme strategy: quality AI insight")
        return await self._theme.create(
            AI_ASPECTS,
            build_prompt=_build_ai_insight_prompt,
            content_type="ai",
            model_key="powerful",
            build_fallback=_build_ai_insight_fallback,
        )


class QualityListStrategy:
    """List theme strategy via :class:`ThemePostHelper`.

    Satisfies ``post_strategies.PostStrategy`` structurally (``async create``).
    """

    __slots__ = ("_theme",)

    STRATEGY_NAME = LIST_STRATEGY_NAME

    def __init__(self, theme_helper: ThemePostHelper) -> None:
        self._theme = theme_helper

    async def create(self) -> Any:
        """Produce a list post (theme → structured → image/fallback)."""
        logger.info("📋 Theme strategy: quality list post")
        return await self._theme.create(
            LIST_THEMES,
            build_prompt=_build_list_prompt,
            content_type="list",
            model_key="creative",
            build_fallback=_build_list_fallback,
        )
