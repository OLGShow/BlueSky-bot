#!/usr/bin/env python3
"""Soft-fail post strategies + duplicate fallback helper — SOFT-002 / SOFT-003.

Extracts former ``AutonomousBlueskyBotV2`` methods:
- ``_create_motivational_moment_post``
- ``_create_emergency_unique_post``
- ``_create_fallback_post_for_duplicate``

Import rules:
- Must not import ``bluesky_bot_v2``.
- Composition root builds ports and registers motivational / emergency.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional, Sequence, Tuple

from .image_post import ThemePostHelper
from .ports import DuplicateFallbackPorts, SoftFailPorts, ThemePostPorts

logger = logging.getLogger(__name__)

# Stable config / learning / registry keys (do not rename).
MOTIVATIONAL_STRATEGY_NAME = "_create_motivational_moment_post"
EMERGENCY_STRATEGY_NAME = "_create_emergency_unique_post"

MOTIVATION_THEMES: Sequence[str] = (
    "преодоление трудностей",
    "достижение целей",
    "личностный рост",
    "начинания и проекты",
    "прогресс и развитие",
)

EMERGENCY_THEMES: Sequence[str] = (
    "момент рефлексии",
    "случайная мысль",
    "настроение дня",
    "простое наблюдение",
)

# Fallback chain: (strategy key, display label) — order is behavioral.
DEFAULT_FALLBACK_CHAIN: Sequence[Tuple[str, str]] = (
    ("_create_personal_opinion_post", "личное мнение"),
    ("_create_quality_ai_insight", "AI инсайт"),
    ("_create_quality_tip_post", "совет из опыта"),
    ("_create_quality_discussion", "дискуссия"),
    ("_create_motivational_moment_post", "мотивационный момент"),
)


def _build_motivational_prompt(selected_theme: str) -> str:
    return f"""
            Create an inspiring, non-cliche motivational post about "{selected_theme}".
            Provide the output in JSON format with "post_text" (in English, 150-200 characters, fresh and engaging) and "hashtags" (in English, 3 relevant tags).

            Example for "achieving goals":
            {{
              "post_text": "Цель не в том, чтобы никогда не падать, а в том, чтобы каждый раз находить новый способ подняться. Какой ваш следующий подъем? 🚀",
              "hashtags": "#мотивация #цели #рост #упорство"
            }}
            """


def _build_motivational_fallback(_selected_theme: str) -> Dict[str, str]:
    current_time = datetime.now().strftime("%H:%M")
    return {
        "post_text": (
            f"💭 Thought of the day ({current_time}):\n\n"
            "What motivates you to move forward right now?"
        ),
        "hashtags": "#motivation #thoughts #development",
    }


def _build_emergency_prompt(selected_theme: str) -> str:
    return f"""
            Create a short, spontaneous post about "{selected_theme}".
            Provide the output in JSON format with "post_text" (in English, 120-180 characters, simple and human-like) and "hashtags" (in English, 2-3 relevant tags).

            Example for "random thought":
            {{
              "post_text": "Иногда самые простые моменты приносят больше всего радости. Замечали? ✨",
              "hashtags": "#момент #жизнь #мысли"
            }}
            """


def _build_emergency_fallback(_selected_theme: str) -> Dict[str, str]:
    timestamp = datetime.now().strftime("%d.%m %H:%M:%S")
    return {
        "post_text": (
            f"💭 Random thought of the moment:\n\n"
            f"What's on your mind right now? ({timestamp})"
        ),
        "hashtags": "#moment #thoughts",
    }


def _soft_fail_to_theme_ports(ports: SoftFailPorts) -> ThemePostPorts:
    return ThemePostPorts(content=ports.content, image=ports.image)


class MotivationalMomentStrategy:
    """Motivational soft-fail post via ThemePostHelper."""

    __slots__ = ("_theme",)

    STRATEGY_NAME = MOTIVATIONAL_STRATEGY_NAME

    def __init__(self, ports: SoftFailPorts) -> None:
        self._theme = ThemePostHelper(_soft_fail_to_theme_ports(ports))

    async def create(self) -> Any:
        return await self._theme.create(
            MOTIVATION_THEMES,
            build_prompt=_build_motivational_prompt,
            content_type="motivational",
            model_key="creative",
            build_fallback=_build_motivational_fallback,
            image_topic=lambda theme: theme,
        )


class EmergencyUniqueStrategy:
    """Last-resort unique emergency post via ThemePostHelper."""

    __slots__ = ("_theme",)

    STRATEGY_NAME = EMERGENCY_STRATEGY_NAME

    def __init__(self, ports: SoftFailPorts) -> None:
        self._theme = ThemePostHelper(_soft_fail_to_theme_ports(ports))

    async def create(self) -> Any:
        return await self._theme.create(
            EMERGENCY_THEMES,
            build_prompt=_build_emergency_prompt,
            content_type="emergency",
            model_key="fast",
            build_fallback=_build_emergency_fallback,
            image_topic=lambda theme: theme,
        )


class DuplicateFallbackHelper:
    """Try fallback strategies until unique; otherwise emergency.

    Parity with ``_create_fallback_post_for_duplicate``.
    """

    __slots__ = ("_ports", "_chain")

    def __init__(
        self,
        ports: DuplicateFallbackPorts,
        *,
        chain: Sequence[Tuple[str, str]] = DEFAULT_FALLBACK_CHAIN,
    ) -> None:
        self._ports = ports
        self._chain = tuple(chain)

    async def create(self) -> Optional[Any]:
        logger.info("🎭 Создание fallback поста для замены дубликата...")

        for func_name, strategy_name in self._chain:
            try:
                strategy_func = self._ports.lookup.lookup(func_name)
                if strategy_func is None:
                    logger.warning(
                        "⚠️ Fallback стратегия '%s' (%s) недоступна — пропускаем",
                        strategy_name,
                        func_name,
                    )
                    continue
                logger.info("🔄 Пробуем стратегию: %s", strategy_name)
                post = await strategy_func()

                if post:
                    url = getattr(post, "url", None)
                    image_url = getattr(post, "image_url", None)
                    if not self._ports.duplicates.is_duplicate(
                        post.text, url, image_url
                    ):
                        logger.info(
                            "✅ Успешно создан fallback пост: %s", strategy_name
                        )
                        return post
                    logger.info(
                        "🔄 Fallback стратегия '%s' тоже дубликат, пробуем следующую",
                        strategy_name,
                    )
            except Exception as e:
                logger.warning(
                    "⚠️ Ошибка в fallback стратегии '%s': %s", strategy_name, e
                )
                continue

        logger.warning(
            "⚠️ Все fallback стратегии не сработали, создаем экстренный пост"
        )
        return await self._ports.emergency.create()
