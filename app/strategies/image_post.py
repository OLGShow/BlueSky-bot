#!/usr/bin/env python3
"""Shared image + theme post helpers — ADR-001 / STRAT-004.

Extracts former ``AutonomousBlueskyBotV2._create_post_with_image_generation``
and ``_quality_theme_post`` behind ports so later strategy families reuse
one path without importing the bot.

Import rules:
- Must not import ``bluesky_bot_v2``.
- Composition root builds :class:`~strategies.ports.ImagePostPorts` /
  :class:`~strategies.ports.ThemePostPorts` and injects helpers.
"""

from __future__ import annotations

import logging
import random
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Mapping,
    Optional,
    Sequence,
)

from .ports import ImagePostPorts, ThemePostPorts

logger = logging.getLogger(__name__)

# content_creation_func / fallback_func shapes from the bot helper.
ContentCreator = Callable[[], Awaitable[Optional[Mapping[str, Any]]]]
FallbackCreator = Callable[[], Awaitable[Any]]
ThemePromptBuilder = Callable[[str], str]
ThemeFallbackBuilder = Callable[[str], Dict[str, str]]
ThemeImageTopic = Callable[[str], str]


class ImagePostHelper:
    """Create a post from structured content + optional generated image.

    Parity with ``_create_post_with_image_generation``:
    - empty structured → fallback (dict / str / ready post) or ``None``
    - image miss / upload miss → text-only post
    """

    __slots__ = ("_ports",)

    def __init__(self, ports: ImagePostPorts) -> None:
        self._ports = ports

    async def create(
        self,
        content_creation_func: ContentCreator,
        image_prompt_text: str,
        content_type: str,
        fallback_func: Optional[FallbackCreator] = None,
    ) -> Any:
        """Produce a formatted post (with image when generation succeeds)."""
        structured_content = await content_creation_func()

        if not structured_content:
            logger.warning(
                "⚠️ Функция создания контента для '%s' вернула пустой результат.",
                content_type,
            )
            return await self._resolve_empty_content(content_type, fallback_func)

        post_text = structured_content.get("post_text", "")
        hashtags = structured_content.get("hashtags", "")
        final_post_text = f"{post_text}\n\n{hashtags}".strip()

        image_prompt = await self._ports.image_prompt.create_prompt(
            image_prompt_text
        )
        image_data = await self._ports.image_gen.generate_image_data(image_prompt)

        if image_data:
            logger.info("✅ Изображение для поста типа '%s' сгенерировано.", content_type)
            image_blob = await self._ports.image_upload.upload(image_data)
            if image_blob:
                alt_text = f"Арт-иллюстрация на тему: {image_prompt_text[:80]}..."
                return self._ports.posts.create_post(
                    final_post_text,
                    content_type=content_type,
                    image_blob=image_blob,
                    image_alt_text=alt_text,
                )

        logger.warning(
            "⚠️ Не удалось сгенерировать изображение для '%s', публикуем только текст.",
            content_type,
        )
        return self._ports.posts.create_post(
            final_post_text, content_type=content_type
        )

    async def _resolve_empty_content(
        self,
        content_type: str,
        fallback_func: Optional[FallbackCreator],
    ) -> Any:
        if not fallback_func:
            return None
        fallback_content = await fallback_func()
        if isinstance(fallback_content, dict):
            post_text = fallback_content.get("post_text", "")
            hashtags = fallback_content.get("hashtags", "")
            final_post_text = f"{post_text}\n\n{hashtags}".strip()
            return self._ports.posts.create_post(
                final_post_text, content_type=content_type
            )
        if isinstance(fallback_content, str):
            return self._ports.posts.create_post(
                fallback_content, content_type=content_type
            )
        return fallback_content


class ThemePostHelper:
    """Pick a theme → structured LLM → :class:`ImagePostHelper`.

    Parity with ``_quality_theme_post`` for ai_insight / list (STRAT-006).
    """

    __slots__ = ("_content", "_image")

    def __init__(self, ports: ThemePostPorts) -> None:
        self._content = ports.content
        self._image = ImagePostHelper(ports.image)

    @property
    def image_helper(self) -> ImagePostHelper:
        """Shared image helper (families may reuse without a second instance)."""
        return self._image

    async def create(
        self,
        themes: Sequence[str],
        *,
        build_prompt: ThemePromptBuilder,
        content_type: str,
        model_key: str,
        build_fallback: ThemeFallbackBuilder,
        image_topic: Optional[ThemeImageTopic] = None,
    ) -> Any:
        """Theme strategy: random theme → structured AI → fallback → image post."""
        selected_theme = random.choice(list(themes))

        async def content_creator() -> Optional[Mapping[str, Any]]:
            return await self._content.generate(
                build_prompt(selected_theme),
                model_key=model_key,
            )

        async def fallback_creator() -> Dict[str, str]:
            return build_fallback(selected_theme)

        topic = image_topic(selected_theme) if image_topic else selected_theme
        return await self._image.create(
            content_creator,
            topic,
            content_type,
            fallback_creator,
        )
