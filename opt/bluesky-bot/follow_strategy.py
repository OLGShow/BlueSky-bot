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
    Tuple,
    runtime_checkable,
)

from agent_decision_log import AgentDecisionLog

logger = logging.getLogger(__name__)

# Discrete follow-quality reasons for agent_decision_log (W1-007).
REASON_QUALITY_OK = "quality_ok"
REASON_KEYWORD = "keyword"
REASON_LIKED_ENOUGH = "liked_enough"
REASON_REJECTED = "rejected"

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


@dataclass(frozen=True)
class FollowPolicy:
    """Tunable follow growth knobs (from ``bot_config.follow_strategy``)."""

    every_n_cycles: int = 2
    max_follows_per_pass: int = 3
    require_bio_keyword: bool = False
    min_likes_for_follow: int = 2
    timeline_min_engagement: int = 30
    suggestions_limit: int = 40
    timeline_limit: int = 30

    @classmethod
    def from_bot_config(cls, config: Optional[dict] = None) -> "FollowPolicy":
        raw = (config or {}).get("follow_strategy") or {}
        return cls(
            every_n_cycles=max(1, int(raw.get("every_n_cycles", 2))),
            max_follows_per_pass=max(1, int(raw.get("max_follows_per_pass", 3))),
            require_bio_keyword=bool(raw.get("require_bio_keyword", False)),
            min_likes_for_follow=max(1, int(raw.get("min_likes_for_follow", 2))),
            timeline_min_engagement=max(
                0, int(raw.get("timeline_min_engagement", 30))
            ),
            suggestions_limit=max(10, int(raw.get("suggestions_limit", 40))),
            timeline_limit=max(10, int(raw.get("timeline_limit", 30))),
        )


def should_follow_user(
    actor: Any,
    *,
    keywords: Sequence[str] = DEFAULT_FOLLOW_KEYWORDS,
    require_bio_keyword: bool = False,
    liked_count: int = 0,
    min_likes_for_follow: int = 2,
) -> Tuple[bool, str]:
    """Heuristic: quality filters + optional bio keywords / prior likes.

    Returns ``(ok, reason)`` where accept reasons are:
    - ``quality_ok`` — quality gates passed and bio keyword not required
    - ``keyword`` — bio keyword match (when ``require_bio_keyword``)
    - ``liked_enough`` — prior likes threshold (when keyword missing)
    Reject reason is ``rejected``.
    """
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
        logger.info(
            "      prior_likes=%s require_keyword=%s",
            liked_count,
            require_bio_keyword,
        )

        if followers_count > 100000:
            logger.info(
                "      ❌ Слишком популярный пользователь (%s подписчиков)",
                followers_count,
            )
            return False, REASON_REJECTED
        if following_count > followers_count * 5 and followers_count > 0:
            logger.info(
                "      ❌ Подозрительное соотношение подписок (%s vs %s)",
                following_count,
                followers_count,
            )
            return False, REASON_REJECTED
        if posts_count < 3:
            logger.info("      ❌ Низкая активность (%s постов)", posts_count)
            return False, REASON_REJECTED
        if posts_count == 0 and followers_count == 0 and following_count == 0:
            logger.info("      ❌ Совершенно новый аккаунт без активности")
            return False, REASON_REJECTED

        has_keyword = keyword_score >= 1
        liked_enough = liked_count >= min_likes_for_follow
        if require_bio_keyword:
            if has_keyword:
                result, reason = True, REASON_KEYWORD
            elif liked_enough:
                result, reason = True, REASON_LIKED_ENOUGH
            else:
                result, reason = False, REASON_REJECTED
            detail = (
                f"{reason} (keyword={has_keyword} liked_enough={liked_enough} "
                f"need keyword or >={min_likes_for_follow} likes)"
            )
        else:
            # Quality gates alone — growth mode (C soft)
            result, reason = True, REASON_QUALITY_OK
            detail = "quality_ok (bio keyword not required)"

        logger.info(
            "      %s Итоговое решение: %s",
            "✅" if result else "❌",
            detail,
        )
        return result, reason
    except Exception as e:
        logger.error("Ошибка анализа пользователя: %s", e)
        return False, REASON_REJECTED


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

    def liked_count_for(self, did: str) -> int: ...

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
    _liked_count_for: Callable[[str], int] = lambda _did: 0
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

    def liked_count_for(self, did: str) -> int:
        try:
            return int(self._liked_count_for(did) or 0)
        except Exception:
            return 0

    @property
    def followed_users(self) -> MutableSet[str]:
        return self._followed_users


class FollowStrategyOrchestrator:
    """Suggestions then timeline follow sources (parity with bot)."""

    __slots__ = ("_ports", "_policy", "_decision_log")

    def __init__(
        self,
        ports: CallableFollowPorts,
        policy: Optional[FollowPolicy] = None,
        decision_log: Optional[AgentDecisionLog] = None,
    ) -> None:
        self._ports = ports
        self._policy = policy or FollowPolicy()
        self._decision_log = decision_log

    def _log_follow(
        self,
        *,
        source: str,
        reason: str,
        did: str,
        handle: str,
        liked_count: int = 0,
    ) -> None:
        """Record outbound follow quality (W1-007). Never raises."""
        log = self._decision_log
        if log is None:
            return
        try:
            log.log(
                domain="follow",
                action="follow",
                arm=str(source or ""),
                reason=str(reason or REASON_QUALITY_OK),
                context={
                    "did": did,
                    "handle": handle,
                    "liked_count": int(liked_count or 0),
                },
            )
        except Exception as exc:
            logger.warning("follow decision_log failed: %s", exc)

    async def run(self) -> None:
        """Fill up to ``max_follows_per_pass`` across suggestions then timeline."""
        try:
            cap = self._policy.max_follows_per_pass
            followed = await self.from_suggestions(max_follows=cap)
            if followed < cap:
                followed += await self.from_timeline(max_follows=cap - followed)
            logger.info(
                "📊 Follow pass done: %s/%s (every_n=%s require_kw=%s)",
                followed,
                cap,
                self._policy.every_n_cycles,
                self._policy.require_bio_keyword,
            )
        except Exception as e:
            logger.error("❌ Ошибка стратегии подписок: %s", e)

    async def from_suggestions(self, *, max_follows: Optional[int] = None) -> int:
        ports = self._ports
        policy = self._policy
        if max_follows is None:
            max_follows = policy.max_follows_per_pass
        try:
            suggestions = await ports.get_suggestions(limit=policy.suggestions_limit)
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

                    liked = ports.liked_count_for(profile.did)
                    ok, reason = should_follow_user(
                        profile,
                        require_bio_keyword=policy.require_bio_keyword,
                        liked_count=liked,
                        min_likes_for_follow=policy.min_likes_for_follow,
                    )
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
                                self._log_follow(
                                    source="suggestions",
                                    reason=reason,
                                    did=profile.did,
                                    handle=profile.handle,
                                    liked_count=liked,
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

    async def from_timeline(self, *, max_follows: Optional[int] = None) -> int:
        ports = self._ports
        policy = self._policy
        if max_follows is None:
            max_follows = policy.max_follows_per_pass
        try:
            timeline = await ports.get_timeline(limit=policy.timeline_limit)
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
                    liked = ports.liked_count_for(full_profile.did)

                    logger.info(
                        "🔍 Автор популярного поста: @%s", full_profile.handle
                    )
                    logger.info("    Вовлеченность поста: %s", post_engagement)
                    logger.info(
                        "    Подписчики: %s, Посты: %s", followers, posts_count
                    )

                    quality_ok, reason = should_follow_user(
                        full_profile,
                        require_bio_keyword=policy.require_bio_keyword,
                        liked_count=liked,
                        min_likes_for_follow=policy.min_likes_for_follow,
                    )
                    if (
                        quality_ok
                        and followers > 10
                        and followers < 50000
                        and posts_count > 5
                        and post_engagement > policy.timeline_min_engagement
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
                                self._log_follow(
                                    source="timeline",
                                    reason=reason,
                                    did=full_profile.did,
                                    handle=full_profile.handle,
                                    liked_count=liked,
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
