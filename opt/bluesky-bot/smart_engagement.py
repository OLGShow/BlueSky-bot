#!/usr/bin/env python3
"""Smart engagement timeline orchestration — Phase 7 / ENG-001.

Extracts former ``AutonomousBlueskyBotV2.smart_engagement`` above
``EngagementService`` (fetch → score → like/repost).

Import rules:
- Must not import ``bluesky_bot_v2``.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import (
    Any,
    Awaitable,
    Callable,
    List,
    Mapping,
    MutableSequence,
    MutableSet,
    Optional,
    Protocol,
    Sequence,
    runtime_checkable,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class TimelinePagePort(Protocol):
    async def fetch(
        self, *, limit: int, cursor: Optional[str] = None
    ) -> Any: ...


@runtime_checkable
class RelevancePort(Protocol):
    def score(self, text_lower: str, post: Any) -> float: ...


@runtime_checkable
class RepostPolicyPort(Protocol):
    def check(
        self,
        text: str,
        author_did: Optional[str],
        post_created: Optional[datetime],
        recent_authors: Sequence[str],
    ) -> tuple: ...


@dataclass
class CallableTimelinePage:
    _fetch: Callable[..., Awaitable[Any]]

    async def fetch(
        self, *, limit: int, cursor: Optional[str] = None
    ) -> Any:
        if cursor is None:
            return await self._fetch(limit=limit)
        return await self._fetch(limit=limit, cursor=cursor)


@dataclass
class CallableRelevance:
    _score: Callable[[str, Any], float]

    def score(self, text_lower: str, post: Any) -> float:
        return self._score(text_lower, post)


@dataclass
class CallableRepostPolicy:
    _check: Callable[..., tuple]

    def check(
        self,
        text: str,
        author_did: Optional[str],
        post_created: Optional[datetime],
        recent_authors: Sequence[str],
    ) -> tuple:
        return self._check(text, author_did, post_created, recent_authors)


@dataclass
class SmartEngagementPorts:
    """Dependencies for :class:`SmartEngagementOrchestrator`."""

    timeline: TimelinePagePort
    relevance: RelevancePort
    like: Callable[..., Awaitable[bool]]
    repost: Callable[..., Awaitable[bool]]
    repost_policy: RepostPolicyPort
    update_relationship: Callable[[str, str, float], None]
    get_my_did: Callable[[], Optional[str]]
    reposted_uris: MutableSet[str]
    recent_repost_authors: MutableSequence[str]
    set_trend_snippets: Callable[[Sequence[str]], None]
    get_session_likes: Callable[[], int]
    bump_errors: Callable[[], None]
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    # PLRN-011: optional topic bandit multipliers + like ledger callback
    infer_topic: Optional[Callable[[str], str]] = None
    topic_multiplier: Optional[Callable[[str], float]] = None
    on_like_action: Optional[Callable[..., None]] = None


@dataclass
class SmartEngagementConfig:
    """Resolved engagement/relevance knobs for one run."""

    timeline_page_limit: int = 100
    timeline_pages: int = 3
    like_threshold: float = 0.20
    static_repost_threshold: float = 0.40
    comment_threshold: float = 0.65
    repost_probability: float = 0.30
    comment_probability: float = 0.0
    max_reposts: int = 2
    max_comments: int = 0
    threshold_mode: str = "fixed"
    quantile_p: float = 0.85
    min_threshold: float = 0.35
    fallback_min_posts: int = 30
    max_interactions: int = 5
    compliant_no_comments: bool = True

    @classmethod
    def from_bot_config(
        cls,
        config: Mapping[str, Any],
        *,
        max_interactions: int,
        compliant_no_comments: bool = True,
    ) -> "SmartEngagementConfig":
        engagement_settings = config.get("engagement_settings", {}) or {}
        rel_settings = config.get("relevance_settings", {}) or {}
        page_limit = int(engagement_settings.get("timeline_page_limit", 100))
        max_pages = int(engagement_settings.get("timeline_pages", 3))
        return cls(
            timeline_page_limit=max(20, min(page_limit, 100)),
            timeline_pages=max(1, min(max_pages, 5)),
            like_threshold=rel_settings.get("like_threshold", 0.20),
            static_repost_threshold=engagement_settings.get(
                "repost_threshold", 0.40
            ),
            comment_threshold=engagement_settings.get("comment_threshold", 0.65),
            repost_probability=engagement_settings.get("repost_probability", 0.30),
            comment_probability=engagement_settings.get("comment_probability", 0),
            max_reposts=engagement_settings.get("max_reposts_per_cycle", 2),
            max_comments=engagement_settings.get("max_comments_per_cycle", 0),
            threshold_mode=engagement_settings.get(
                "repost_threshold_mode", "fixed"
            ),
            quantile_p=engagement_settings.get("repost_quantile", 0.85),
            min_threshold=engagement_settings.get("repost_min_threshold", 0.35),
            fallback_min_posts=engagement_settings.get(
                "repost_fallback_min_posts", 30
            ),
            max_interactions=max_interactions,
            compliant_no_comments=compliant_no_comments,
        )


class SmartEngagementOrchestrator:
    """Timeline pages → score → like/repost via EngagementService ports."""

    __slots__ = ("_ports",)

    def __init__(self, ports: SmartEngagementPorts) -> None:
        self._ports = ports

    async def run(self, cfg: SmartEngagementConfig) -> None:
        """One smart-engagement cycle (parity with former bot method)."""
        ports = self._ports
        try:
            feed_items: List[Any] = []
            cursor = None
            for _ in range(cfg.timeline_pages):
                timeline_page = await ports.timeline.fetch(
                    limit=cfg.timeline_page_limit, cursor=cursor
                )
                page_feed = getattr(timeline_page, "feed", []) or []
                feed_items.extend(page_feed)
                cursor = getattr(timeline_page, "cursor", None)
                if not cursor or not page_feed:
                    break

            interactions = 0
            posts_analyzed = 0
            high_relevance_posts = 0
            reposts_made = 0
            comments_made = 0

            logger.info(
                "📰 Получено %s постов для анализа (страниц: %s, limit/page: %s)",
                len(feed_items),
                cfg.timeline_pages,
                cfg.timeline_page_limit,
            )

            scored_posts: List[tuple] = []
            trend_snippets: List[str] = []
            my_did = ports.get_my_did()
            for post in feed_items:
                if not hasattr(post.post.record, "text"):
                    continue
                author_did = getattr(post.post.author, "did", None)
                if not author_did or (my_did and author_did == my_did):
                    continue
                text = post.post.record.text
                trend_snippets.append(text[:200])
                score = ports.relevance.score(text.lower(), post)
                scored_posts.append((post, text, author_did, score))

            ports.set_trend_snippets(trend_snippets[:100])
            posts_analyzed = len(scored_posts)

            all_scores = [s for _, _, _, s in scored_posts]
            if (
                cfg.threshold_mode == "dynamic_quantile"
                and len(all_scores) >= cfg.fallback_min_posts
            ):
                sorted_scores = sorted(all_scores)
                idx = int(len(sorted_scores) * cfg.quantile_p)
                idx = min(idx, len(sorted_scores) - 1)
                repost_threshold = max(cfg.min_threshold, sorted_scores[idx])
                logger.info(
                    "🎲 Динамический порог репоста: P%s=%.2f -> threshold=%.2f (min=%.2f)",
                    int(cfg.quantile_p * 100),
                    sorted_scores[idx],
                    repost_threshold,
                    cfg.min_threshold,
                )
            else:
                repost_threshold = cfg.static_repost_threshold
                logger.info(
                    "🎯 Фиксированный порог репоста: %.2f (постов %s < %s или mode=fixed)",
                    repost_threshold,
                    len(all_scores),
                    cfg.fallback_min_posts,
                )

            if cfg.max_reposts == 0:
                logger.info("🚫 Репосты ПОЛНОСТЬЮ ОТКЛЮЧЕНЫ (max_reposts=0)")

            score_dist = {
                "0.0-0.1": 0,
                "0.1-0.2": 0,
                "0.2-0.3": 0,
                "0.3-0.4": 0,
                "0.4-0.5": 0,
                "0.5+": 0,
            }
            for s in all_scores:
                if s < 0.1:
                    score_dist["0.0-0.1"] += 1
                elif s < 0.2:
                    score_dist["0.1-0.2"] += 1
                elif s < 0.3:
                    score_dist["0.2-0.3"] += 1
                elif s < 0.4:
                    score_dist["0.3-0.4"] += 1
                elif s < 0.5:
                    score_dist["0.4-0.5"] += 1
                else:
                    score_dist["0.5+"] += 1
            logger.info("📊 Распределение score: %s", score_dist)

            scored_posts.sort(key=lambda x: x[3], reverse=True)

            for post, text, author_did, relevance_score in scored_posts:
                if interactions >= cfg.max_interactions:
                    break

                topic: Optional[str] = None
                effective = float(relevance_score)
                if ports.topic_multiplier and ports.infer_topic:
                    topic = ports.infer_topic(text)
                    effective = float(relevance_score) * float(
                        ports.topic_multiplier(topic)
                    )

                author_handle = getattr(post.post.author, "handle", "unknown")
                logger.info(
                    "🔍 @%s: score=%.2f eff=%.2f | %s%s",
                    author_handle,
                    relevance_score,
                    effective,
                    text[:80],
                    "..." if len(text) > 80 else "",
                )

                if effective < cfg.like_threshold:
                    continue

                high_relevance_posts += 1

                try:
                    liked = await ports.like(
                        uri=post.post.uri,
                        cid=post.post.cid,
                        score=effective,
                        author_did=author_did,
                        author_handle=author_handle,
                    )
                    if liked:
                        interactions += 1
                        logger.info("❤️ Лайк поставлен!")
                        if ports.on_like_action:
                            try:
                                mult = 1.0
                                if ports.topic_multiplier and topic:
                                    mult = float(
                                        ports.topic_multiplier(topic)
                                    )
                                ports.on_like_action(
                                    kind="like",
                                    topic=topic or "_other",
                                    uri=post.post.uri,
                                    ts=datetime.now(timezone.utc).isoformat(),
                                    rewarded_checks=[],
                                    multiplier=mult,
                                    score=float(relevance_score),
                                    effective_score=float(effective),
                                )
                            except Exception as cb_err:
                                logger.warning(
                                    "on_like_action failed: %s", cb_err
                                )
                        await ports.sleep(random.uniform(3, 7))

                    if (
                        effective >= repost_threshold
                        and reposts_made < cfg.max_reposts
                        and random.random() < cfg.repost_probability
                        and post.post.uri not in ports.reposted_uris
                    ):
                        post_created = None
                        try:
                            raw_ts = getattr(post.post.record, "created_at", None)
                            if raw_ts:
                                post_created = datetime.fromisoformat(
                                    str(raw_ts).replace("Z", "+00:00")
                                ).replace(tzinfo=None)
                        except Exception:
                            pass
                        policy_ok, policy_reason = ports.repost_policy.check(
                            text,
                            author_did,
                            post_created,
                            list(ports.recent_repost_authors),
                        )
                        if policy_ok:
                            reposted = await ports.repost(
                                uri=post.post.uri,
                                cid=post.post.cid,
                                score=effective,
                                author_did=author_did,
                            )
                            if reposted:
                                reposts_made += 1
                                logger.info(
                                    "🔄 Репост выполнен! (score=%.2f, #%s/%s)",
                                    effective,
                                    reposts_made,
                                    cfg.max_reposts,
                                )
                                await ports.sleep(random.uniform(5, 10))
                        else:
                            logger.info(
                                "🛡️ Репост заблокирован policy: %s", policy_reason
                            )

                    if author_did:
                        ports.update_relationship(
                            author_did, "engagement", effective
                        )

                except Exception as e:
                    logger.error("Ошибка взаимодействия: %s", e)

                await ports.sleep(random.uniform(5, 12))

            logger.info("📊 Итого проанализировано: %s постов", posts_analyzed)
            logger.info(
                "🎯 Высокая релевантность: %s постов", high_relevance_posts
            )
            logger.info(
                "❤️ Лайков поставлено (этот цикл): %s | всего за сессию: %s",
                interactions,
                ports.get_session_likes(),
            )
            logger.info("🔄 Репостов сделано: %s", reposts_made)
            if cfg.compliant_no_comments:
                logger.info("💬 Комментарии: ОТКЛЮЧЕНЫ (BlueSky compliance)")
            else:
                logger.info("💬 Комментариев отправлено: %s", comments_made)

            if posts_analyzed > 0:
                relevance_rate = (high_relevance_posts / posts_analyzed) * 100
                like_rate = (interactions / posts_analyzed) * 100
                repost_rate = (reposts_made / posts_analyzed) * 100
                comment_rate = (comments_made / posts_analyzed) * 100
                logger.info("📈 Показатели эффективности:")
                logger.info(
                    "   📊 Процент релевантных постов: %.1f%%", relevance_rate
                )
                logger.info("   ❤️ Процент лайков: %.1f%%", like_rate)
                logger.info("   🔄 Процент репостов: %.1f%%", repost_rate)
                logger.info("   💬 Процент комментариев: %.1f%%", comment_rate)
                if high_relevance_posts > 0:
                    logger.info(
                        "   🎯 Конверсия релевантности: %.1f%%",
                        (interactions / high_relevance_posts) * 100,
                    )
                else:
                    logger.info("   🎯 Конверсия релевантности: 0%")

        except Exception as e:
            logger.error("❌ Ошибка умного взаимодействия: %s", e)
            ports.bump_errors()
