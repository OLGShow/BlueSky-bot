#!/usr/bin/env python3
"""Engage with posts from official trend feeds (getFeed via link).

Uses filtered :class:`~trends.TrendItem` list only — never touches RSS.

Import rules:
- Must not import ``bluesky_bot_v2``.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import (
    Any,
    Awaitable,
    Callable,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    runtime_checkable,
)

from trends import BlueSkyTrendingTracker, TrendItem, TrendsConfig

logger = logging.getLogger(__name__)


@runtime_checkable
class FeedPagePort(Protocol):
    async def fetch(self, feed_uri: str, *, limit: int) -> Any: ...


@runtime_checkable
class RelevancePort(Protocol):
    def score(self, text_lower: str, post: Any) -> float: ...


@dataclass
class CallableFeedPage:
    _fetch: Callable[..., Awaitable[Any]]

    async def fetch(self, feed_uri: str, *, limit: int) -> Any:
        return await self._fetch(feed_uri, limit=limit)


@dataclass
class CallableRelevance:
    _score: Callable[[str, Any], float]

    def score(self, text_lower: str, post: Any) -> float:
        return self._score(text_lower, post)


@dataclass
class TrendsEngagementPorts:
    """Dependencies for :class:`TrendsEngagementOrchestrator`."""

    tracker: BlueSkyTrendingTracker
    feed: FeedPagePort
    relevance: RelevancePort
    like: Callable[..., Awaitable[bool]]
    get_my_did: Callable[[], Optional[str]]
    sleep: Callable[[float], Awaitable[None]]


@dataclass
class TrendsEngagementConfig:
    like_threshold: float = 0.32
    max_likes: int = 3

    @classmethod
    def from_bot_config(
        cls,
        config: Mapping[str, Any],
        *,
        max_likes: int,
    ) -> "TrendsEngagementConfig":
        rel = config.get("relevance_settings", {}) or {}
        return cls(
            like_threshold=float(rel.get("like_threshold", 0.32)),
            max_likes=max(0, int(max_likes)),
        )


class TrendsEngagementOrchestrator:
    """Top filtered trends → getFeed → relevance → like."""

    __slots__ = ("_ports",)

    def __init__(self, ports: TrendsEngagementPorts) -> None:
        self._ports = ports

    async def run(self, cfg: TrendsEngagementConfig) -> int:
        """Return number of likes placed. No-op when trends engagement off."""
        ports = self._ports
        tcfg: TrendsConfig = ports.tracker.cfg
        if (
            not tcfg.enabled
            or not tcfg.use_for_engagement
            or cfg.max_likes <= 0
            or tcfg.engagement_topics_per_cycle <= 0
        ):
            logger.info("Trends engagement skipped (disabled or budget 0)")
            return 0

        trends: Sequence[TrendItem] = await ports.tracker.get_filtered_trends()
        if not trends:
            logger.info("Trends engagement: no filtered topics")
            return 0

        selected = list(trends[: tcfg.engagement_topics_per_cycle])
        likes = 0
        my_did = ports.get_my_did()

        for trend in selected:
            if likes >= cfg.max_likes:
                break
            if not trend.feed_uri:
                logger.debug(
                    "Trend %r has no feed_uri (link=%s)", trend.label, trend.link
                )
                continue
            try:
                page = await ports.feed.fetch(
                    trend.feed_uri,
                    limit=tcfg.engagement_posts_per_topic,
                )
            except Exception as e:
                logger.warning(
                    "getFeed failed for trend %r: %s", trend.label, e
                )
                continue

            feed_items: List[Any] = list(getattr(page, "feed", None) or [])
            if isinstance(page, Mapping):
                feed_items = list(page.get("feed") or [])

            scored: List[tuple] = []
            for entry in feed_items:
                post = getattr(entry, "post", entry)
                if isinstance(entry, Mapping):
                    post = entry.get("post") or entry
                record = getattr(post, "record", None)
                if isinstance(post, Mapping):
                    record = post.get("record")
                text = getattr(record, "text", None)
                if text is None and isinstance(record, Mapping):
                    text = record.get("text")
                if not text:
                    continue
                author = getattr(post, "author", None)
                if isinstance(post, Mapping):
                    author = post.get("author")
                author_did = getattr(author, "did", None)
                if author_did is None and isinstance(author, Mapping):
                    author_did = author.get("did")
                if my_did and author_did == my_did:
                    continue
                # Wrap dict posts for relevance_scoring (expects post.post.*)
                wrapper = entry if hasattr(entry, "post") else _DictPostWrap(post)
                score = ports.relevance.score(str(text).lower(), wrapper)
                scored.append((wrapper, text, author_did, score, author))

            scored.sort(key=lambda x: x[3], reverse=True)
            for wrapper, text, author_did, score, author in scored:
                if likes >= cfg.max_likes:
                    break
                if score < cfg.like_threshold:
                    continue
                uri = _post_attr(wrapper, "uri")
                cid = _post_attr(wrapper, "cid")
                handle = getattr(author, "handle", None)
                if handle is None and isinstance(author, Mapping):
                    handle = author.get("handle")
                if not uri or not cid:
                    continue
                try:
                    ok = await ports.like(
                        uri=uri,
                        cid=cid,
                        score=score,
                        author_did=author_did,
                        author_handle=handle or "unknown",
                    )
                except Exception as e:
                    logger.warning("trend like failed: %s", e)
                    continue
                if ok:
                    likes += 1
                    logger.info(
                        "❤️ Trends like on %r (@%s score=%.2f)",
                        trend.label,
                        handle or "?",
                        score,
                    )
                    await ports.sleep(random.uniform(3, 7))

        logger.info("Trends engagement: %s likes across %s topics", likes, len(selected))
        return likes


class _DictPostWrap:
    """Minimal object so ``relevance_scoring`` can read ``post.post.*``."""

    __slots__ = ("post",)

    def __init__(self, post: Any) -> None:
        self.post = _AttrDict(post) if isinstance(post, Mapping) else post


class _AttrDict:
    __slots__ = ("_data",)

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data = data

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return self._data.get(name)


def _post_attr(wrapper: Any, name: str) -> Any:
    post = getattr(wrapper, "post", wrapper)
    val = getattr(post, name, None)
    if val is None and isinstance(post, Mapping):
        val = post.get(name)
    return val


__all__ = [
    "CallableFeedPage",
    "CallableRelevance",
    "TrendsEngagementConfig",
    "TrendsEngagementOrchestrator",
    "TrendsEngagementPorts",
]
