#!/usr/bin/env python3
"""Quality news/RSS post strategy — ADR-001 / STRAT-002.

Implements the former ``AutonomousBlueskyBotV2._create_quality_news_post``
flow behind :class:`~post_strategies.PostStrategy` using
:class:`~strategies.ports.NewsStrategyPorts` only.

Import rules:
- Must not import ``bluesky_bot_v2``.
- Composition root builds ports and registers this instance under
  ``STRATEGY_NAME`` (``_create_quality_news_post``) in the hybrid registry.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Mapping, Optional, Sequence

from .ports import NewsItem, NewsStrategyPorts

logger = logging.getLogger(__name__)

# Stable config / learning / A/B / registry key (do not rename).
STRATEGY_NAME = "_create_quality_news_post"

# Personal lead-ins used in the structured-content prompt (parity with bot).
PERSONAL_TAKES: Sequence[str] = (
    "Interesting turn! 🤔",
    "Didn't expect this development",
    "This changes a lot in the industry",
    "Wow, what news! 🔥",
    "Curious times...",
    "Worth taking a closer look",
    "Classic! Just as I thought 😏",
)

_DEFAULT_HASHTAGS = "#новости #технологии"
_CANDIDATE_LIMIT = 10
_MIN_TITLE_LEN = 20


class QualityNewsStrategy:
    """News/RSS family strategy: headlines → dedupe → LLM → link card → fallback.

    Satisfies ``post_strategies.PostStrategy`` structurally (``async create``).
    """

    __slots__ = ("_ports",)

    def __init__(self, ports: NewsStrategyPorts) -> None:
        self._ports = ports

    async def create(self) -> Any:
        """Produce a news post, or fall back to the injected opinion path."""
        try:
            return await self._create_news_post()
        except Exception as e:
            logger.error("❌ Ошибка создания новостного поста: %s", e)
            return await self._ports.fallback.create()

    async def _create_news_post(self) -> Any:
        logger.info("🌐 Активация RSS-фидов для новостного поста...")
        news_content = await self._ports.headlines.fetch()

        if not news_content:
            logger.warning("⚠️ RSS-фиды не вернули новости, проверяем источники...")
            urls = list(self._ports.feeds.urls)
            logger.info("📋 Доступно RSS источников: %s", len(urls))
            for i, feed_url in enumerate(urls[:5]):
                source_name = feed_url.split("//")[-1].split("/")[0]
                logger.info("   %s. %s", i + 1, source_name)
            return await self._ports.fallback.create()

        selected_news = self._select_unique_news(news_content)
        if selected_news is None:
            logger.warning("⚠️ Все новости уже были опубликованы или не подходят")
            logger.info("🔄 Переключаемся на альтернативный контент вместо новостей")
            return await self._ports.fallback.create()

        personal_comment = random.choice(list(PERSONAL_TAKES))
        prompt = _build_news_prompt(selected_news["title"], personal_comment)
        structured_content = await self._ports.content.generate(
            prompt, model_key="creative"
        )

        if structured_content:
            return await self._build_from_structured(selected_news, structured_content)

        return await self._ports.fallback.create()

    def _select_unique_news(
        self, news_content: Sequence[NewsItem]
    ) -> Optional[Mapping[str, Any]]:
        for news in news_content[:_CANDIDATE_LIMIT]:
            title = news.get("title", "")
            if len(title) <= _MIN_TITLE_LEN or not news.get("description"):
                continue
            url = news.get("url", "")
            image_url = news.get("image_url", "")
            if not self._ports.duplicates.is_duplicate("", url, image_url):
                logger.info("✅ Выбрана уникальная новость: %s...", title[:50])
                return news
            logger.info("🔄 Пропускаем дубликат новости: %s...", title[:50])
        return None

    async def _build_from_structured(
        self,
        selected_news: Mapping[str, Any],
        structured_content: Mapping[str, Any],
    ) -> Any:
        post_text = structured_content.get("post_text", "")
        hashtags = structured_content.get("hashtags", _DEFAULT_HASHTAGS)
        final_content = f"{post_text}\n\n{hashtags}"

        post = self._ports.posts.create_post(final_content, content_type="news")

        image_url = selected_news.get("image_url")
        if image_url:
            try:
                enhanced_post = await self._ports.link_preview.create_with_preview(
                    final_content,
                    selected_news.get("url", ""),
                    selected_news["title"],
                    selected_news.get("description", ""),
                    image_url,
                )
                if enhanced_post:
                    logger.info("✅ Создан пост с изображением и карточкой ссылки")
                    return enhanced_post
            except Exception as e:
                logger.warning("⚠️ Не удалось создать пост с изображением: %s", e)

        post.url = selected_news.get("url", "")
        post.image_url = selected_news.get("image_url", "")
        return post


def _build_news_prompt(title: str, personal_comment: str) -> str:
    return f"""
            Create a personal social media post about this news: "{title}"
            Start with the personal comment: "{personal_comment}"
            
            Provide the output in JSON format with "post_text" (in English, 150-200 chars, retell the news briefly in your own words, add a natural ending - it can be a question, observation, emoji, or statement) and "hashtags" (in English, 2-3 relevant tags).

            Examples:
            {{
              "post_text": "Interesting turn! 🤔 OpenAI just released a new model with revolutionary capabilities. This could change everything.",
              "hashtags": "#news #AI #technology"
            }}
            {{
              "post_text": "Classic! 🙄 Another tech CEO promises to revolutionize everything. We'll see...",
              "hashtags": "#tech #startup #news"
            }}
            {{
              "post_text": "Wow! New research shows AI can predict weather patterns 10x better than before 🌩️",
              "hashtags": "#science #AI #weather"
            }}
            """
