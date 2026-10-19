#!/usr/bin/env python3
"""Follow strategy orchestration — thin-shell FOL-001.

Extracts former ``should_follow_user``, ``follow_strategy``,
``_follow_from_suggestions``, ``_follow_from_timeline``.

Import rules:
- Must not import ``bluesky_bot_v2``.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import (
    Any,
    Awaitable,
    Callable,
    MutableSet,
    Optional,
    Protocol,
    Sequence,
    runtime_checkable,
)

logger = logging.getLogger(__name__)

DEFAULT_FOLLOW_KEYWORDS: Sequence[str] = (
    "художник",
    "artist",
    "дизайнер",
    "designer",
    "фотограф",
    "photographer",
    "музыкант",
    "musician",
    "писатель",
    "writer",
    "автор",
    "author",
    "программист",
    "developer",
    "разработчик",
    "ai",
    "ии",
    "программирование",
    "технологии",
    "python",
    "javascript",
    "tech",
    "стартап",
    "startup",
    "инновации",
    "наука",
    "исследования",
    "research",
    "учитель",
    "teacher",
    "преподаватель",
    "философ",
    "philosopher",
    "культура",
    "culture",
    "образование",
    "education",
    "блогер",
    "blogger",
    "путешественник",
    "traveler",
    "повар",
    "chef",
    "спортсмен",
    "athlete",
    "природа",
    "nature",
    "экология",
    "ecology",
    "животные",
    "animals",
    "журналист",
    "journalist",
    "психолог",
    "psychologist",
    "врач",
    "doctor",
    "бизнес",
    "business",
    "предприниматель",
    "entrepreneur",
)


def should_follow_user(
    actor: Any,
    *,
    keywords: Sequence[str] = DEFAULT_FOLLOW_KEYWORDS,
) -> bool:
    """Heuristic: description keywords + soft quality filters."""
    try:
        description = (actor.description or "").lower()
        found_keywords = [kw for kw in keywords if kw in description]
        keyword_score = len(found_keywords)

        followers_count = getattr(actor, "followers_count", 0) or 0
        following_count = getattr(actor, "follows_count", 0) or 0
        posts_count = getattr(actor, "posts_count", 0) or 0

        logger.info("    🔍 Анализ критериев:")
        logger.info(
            "      Найденные ключевые слова: %s (score: %s)",
            found_keywords,
            keyword_score,
        )

        if followers_count > 100000:
            logger.info(
                "      ❌ Слишком популярный пользователь (%s подписчиков)",
                followers_count,
            )
            return False
        if following_count > followers_count * 5 and followers_count > 0:
            logger.info(
                "      ❌ Подозрительное соотношение подписок (%s vs %s)",
                following_count,
                followers_count,
            )
            return False
        if posts_count < 3:
            logger.info("      ❌ Низкая активность (%s постов)", posts_count)
            return False
        if posts_count == 0 and followers_count == 0 and following_count == 0:
            logger.info("      ❌ Совершенно новый аккаунт без активности")
            return False

        result = keyword_score >= 1
        logger.info(
            "      %s Итоговое решение: %s ключевых слов >= 1",
            "✅" if result else "❌",
            keyword_score,
        )
        return result
    except Exception as e:
        logger.error("Ошибка анализа пользователя: %s", e)
        return False


@runtime_checkable
class FollowPorts(Protocol):
    """Narrow adapters for follow orchestration."""

    async def get_suggestions(self, *, limit: int = 30) -> Any: ...

    async def get_profile(self, did: str) -> Any: ...

    async def get_timeline(self, *, limit: int = 30) -> Any: ...

    async def follow(
        self, *, did: str, handle: str, source: str
    ) -> bool: ...

    def update_relationship(self, did: str, action: str, score: float) -> None: ...

    def get_my_did(self) -> Optional[str]: ...

    @property
    def followed_users(self) -> MutableSet[str]: ...


@dataclass
class CallableFollowPorts:
    """Composition-root bundle implementing :class:`FollowPorts`."""

    _get_suggestions: Callable[..., Awaitable[Any]]
    _get_profile: Callable[[str], Awaitable[Any]]
    _get_timeline: Callable[..., Awaitable[Any]]
    _follow: Callable[..., Awaitable[bool]]
    _update_relationship: Callable[[str, str, float], None]
    _get_my_did: Callable[[], Optional[str]]
    _followed_users: MutableSet[str]
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    async def get_suggestions(self, *, limit: int = 30) -> Any:
        return await self._get_suggestions(limit=limit)

    async def get_profile(self, did: str) -> Any:
        return await self._get_profile(did)

    async def get_timeline(self, *, limit: int = 30) -> Any:
        return await self._get_timeline(limit=limit)

    async def follow(self, *, did: str, handle: str, source: str) -> bool:
        return await self._follow(did=did, handle=handle, source=source)

    def update_relationship(self, did: str, action: str, score: float) -> None:
        self._update_relationship(did, action, score)

    def get_my_did(self) -> Optional[str]:
        return self._get_my_did()

    @property
    def followed_users(self) -> MutableSet[str]:
        return self._followed_users


class FollowStrategyOrchestrator:
    """Suggestions then timeline follow sources (parity with bot)."""

    __slots__ = ("_ports",)

    def __init__(self, ports: CallableFollowPorts) -> None:
        self._ports = ports

    async def run(self) -> None:
        try:
            for strategy in (self.from_suggestions, self.from_timeline):
                followed = await strategy()
                if followed > 0:
                    break
        except Exception as e:
            logger.error("❌ Ошибка стратегии подписок: %s", e)

    async def from_suggestions(self, *, max_follows: int = 1) -> int:
        ports = self._ports
        try:
            suggestions = await ports.get_suggestions(limit=30)
            actors = getattr(suggestions, "actors", []) or []
            logger.info("👥 Получено %s рекомендаций пользователей", len(actors))

            followed = 0
            users_analyzed = 0

            for actor in actors:
                if followed >= max_follows:
                    break
                users_analyzed += 1
                try:
                    profile = await ports.get_profile(actor.did)
                    followers = getattr(profile, "followers_count", 0) or 0
                    following = getattr(profile, "follows_count", 0) or 0
                    posts = getattr(profile, "posts_count", 0) or 0

                    logger.info(
                        "🔍 Анализ #%s: @%s", users_analyzed, profile.handle
                    )
                    logger.info(
                        "    Описание: %s",
                        (profile.description[:100] if profile.description else "Нет описания"),
                    )
                    logger.info(
                        "    Подписчики: %s, Подписки: %s, Посты: %s",
                        followers,
                        following,
                        posts,
                    )

                    ok = should_follow_user(profile)
                    logger.info(
                        "    Решение: %s",
                        "✅ Подписаться" if ok else "❌ Пропустить",
                    )

                    if ok and profile.did not in ports.followed_users:
                        try:
                            followed_ok = await ports.follow(
                                did=profile.did,
                                handle=profile.handle,
                                source="suggestions",
                            )
                            if followed_ok:
                                logger.info(
                                    "➕ Подписка на @%s выполнена!",
                                    profile.handle,
                                )
                                followed += 1
                            try:
                                ports.update_relationship(profile.did, "follow", 5)
                            except Exception as rel_error:
                                logger.warning(
                                    "⚠️ Ошибка обновления отношений для @%s: %s",
                                    profile.handle,
                                    rel_error,
                                )
                            await ports.sleep(random.uniform(3, 7))
                        except Exception as e:
                            logger.error(
                                "Ошибка подписки на @%s: %s", profile.handle, e
                            )
                    elif profile.did in ports.followed_users:
                        logger.info(
                            "👥 Уже подписаны на @%s, пропускаем", profile.handle
                        )
                except Exception as e:
                    logger.error(
                        "Ошибка получения профиля @%s: %s",
                        getattr(actor, "handle", "?"),
                        e,
                    )
                    continue

            logger.info("📊 Стратегия рекомендаций:")
            logger.info("    Проанализировано: %s пользователей", users_analyzed)
            logger.info("    Подписок сделано: %s", followed)
            return followed
        except Exception as e:
            logger.error("❌ Ошибка стратегии рекомендаций: %s", e)
            return 0

    async def from_timeline(self, *, max_follows: int = 1) -> int:
        ports = self._ports
        try:
            timeline = await ports.get_timeline(limit=30)
            feed = getattr(timeline, "feed", []) or []
            logger.info("📰 Анализ авторов популярных постов из ленты")

            followed = 0
            analyzed_authors: set = set()
            popular_posts = sorted(
                feed,
                key=lambda x: (x.post.like_count or 0)
                + (x.post.repost_count or 0) * 2,
                reverse=True,
            )[:20]

            for post in popular_posts:
                if followed >= max_follows:
                    break
                author = post.post.author
                my_did = ports.get_my_did()
                if author.did in analyzed_authors or (
                    my_did and author.did == my_did
                ):
                    continue
                analyzed_authors.add(author.did)

                try:
                    full_profile = await ports.get_profile(author.did)
                    followers = getattr(full_profile, "followers_count", 0) or 0
                    posts_count = getattr(full_profile, "posts_count", 0) or 0
                    post_engagement = (post.post.like_count or 0) + (
                        post.post.repost_count or 0
                    ) * 2

                    logger.info(
                        "🔍 Автор популярного поста: @%s", full_profile.handle
                    )
                    logger.info("    Вовлеченность поста: %s", post_engagement)
                    logger.info(
                        "    Подписчики: %s, Посты: %s", followers, posts_count
                    )

                    if (
                        followers > 10
                        and followers < 50000
                        and posts_count > 5
                        and post_engagement > 50
                        and full_profile.did not in ports.followed_users
                    ):
                        try:
                            followed_ok = await ports.follow(
                                did=full_profile.did,
                                handle=full_profile.handle,
                                source="timeline",
                            )
                            if followed_ok:
                                logger.info(
                                    "➕ Подписка на автора популярного поста @%s!",
                                    full_profile.handle,
                                )
                                followed += 1
                            try:
                                ports.update_relationship(
                                    full_profile.did, "follow", 7
                                )
                            except Exception as rel_error:
                                logger.warning(
                                    "⚠️ Ошибка обновления отношений для @%s: %s",
                                    full_profile.handle,
                                    rel_error,
                                )
                            await ports.sleep(random.uniform(4, 8))
                        except Exception as e:
                            logger.error(
                                "Ошибка подписки на @%s: %s",
                                full_profile.handle,
                                e,
                            )
                    elif full_profile.did in ports.followed_users:
                        logger.info(
                            "👥 Уже подписаны на автора @%s, пропускаем",
                            full_profile.handle,
                        )
                except Exception as e:
                    logger.error(
                        "Ошибка получения профиля автора @%s: %s",
                        getattr(author, "handle", "?"),
                        e,
                    )
                    continue

            logger.info("📊 Стратегия популярных авторов:")
            logger.info("    Подписок сделано: %s", followed)
            return followed
        except Exception as e:
            logger.error("❌ Ошибка стратегии популярных авторов: %s", e)
            return 0
