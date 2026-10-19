#!/usr/bin/env python3
"""Official Bluesky «Актуальные» trends — getTrends + soft filter + cache.

SoT for live trending topics. Does **not** filter RSS / news pipelines —
``deny_keywords`` here applies only to this module's trend list.

Import rules:
- Must not import ``bluesky_bot_v2``.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
)
from urllib.parse import quote

logger = logging.getLogger(__name__)

DEFAULT_PUBLIC_API = "https://public.api.bsky.app"
GET_TRENDS_PATH = "/xrpc/app.bsky.unspecced.getTrends"
GET_FEED_PATH = "/xrpc/app.bsky.feed.getFeed"

# Soft defaults: take almost the whole top; empty deny = no keyword cuts.
DEFAULT_TRENDS_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "limit": 15,
    "cache_minutes": 45,
    "use_for_posts": True,
    "use_for_engagement": True,
    "deny_keywords": [],
    "allow_categories": [],
    "min_post_count": 0,
    "max_topics": 10,
    "engagement_topics_per_cycle": 3,
    "engagement_posts_per_topic": 5,
    "public_api_base": DEFAULT_PUBLIC_API,
}

_LINK_RE = re.compile(
    r"^/profile/(did:[^/]+)/feed/([^/?#]+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TrendItem:
    """Normalized AppView trend row."""

    topic: str
    display_name: str
    category: str
    link: str
    post_count: int
    feed_uri: str = ""
    description: str = ""
    status: str = ""

    @property
    def label(self) -> str:
        """Human-facing theme string for posts / templates."""
        return self.display_name or self.topic

    def as_legacy_dict(self) -> Dict[str, Any]:
        """Shape expected by DynamicContentGenerator (topic + count)."""
        return {
            "topic": self.label,
            "count": self.post_count,
            "display_name": self.display_name,
            "topic_id": self.topic,
            "category": self.category,
            "link": self.link,
            "post_count": self.post_count,
            "feed_uri": self.feed_uri,
            "description": self.description,
        }


@dataclass
class TrendsConfig:
    """Resolved ``bot_config.trends`` knobs (trends pipeline only)."""

    enabled: bool = True
    limit: int = 15
    cache_minutes: int = 45
    use_for_posts: bool = True
    use_for_engagement: bool = True
    deny_keywords: Sequence[str] = field(default_factory=list)
    allow_categories: Sequence[str] = field(default_factory=list)
    min_post_count: int = 0
    max_topics: int = 10
    engagement_topics_per_cycle: int = 3
    engagement_posts_per_topic: int = 5
    public_api_base: str = DEFAULT_PUBLIC_API

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]]) -> "TrendsConfig":
        data = dict(DEFAULT_TRENDS_CONFIG)
        if raw:
            data.update(dict(raw))
        deny = data.get("deny_keywords") or []
        allow = data.get("allow_categories") or []
        return cls(
            enabled=bool(data.get("enabled", True)),
            limit=max(1, min(int(data.get("limit", 15)), 25)),
            cache_minutes=max(1, min(int(data.get("cache_minutes", 45)), 180)),
            use_for_posts=bool(data.get("use_for_posts", True)),
            use_for_engagement=bool(data.get("use_for_engagement", True)),
            deny_keywords=tuple(str(x).lower() for x in deny),
            allow_categories=tuple(str(x).lower() for x in allow),
            min_post_count=max(0, int(data.get("min_post_count", 0))),
            max_topics=max(1, min(int(data.get("max_topics", 10)), 25)),
            engagement_topics_per_cycle=max(
                0, min(int(data.get("engagement_topics_per_cycle", 3)), 10)
            ),
            engagement_posts_per_topic=max(
                1, min(int(data.get("engagement_posts_per_topic", 5)), 25)
            ),
            public_api_base=str(
                data.get("public_api_base") or DEFAULT_PUBLIC_API
            ).rstrip("/"),
        )


def feed_uri_from_link(link: str) -> str:
    """Map AppView sidebar link → ``at://did/.../app.bsky.feed.generator/id``."""
    if not link:
        return ""
    text = str(link).strip()
    if text.startswith("at://"):
        return text
    m = _LINK_RE.match(text)
    if not m:
        return ""
    did, feed_id = m.group(1), m.group(2)
    return f"at://{did}/app.bsky.feed.generator/{feed_id}"


def normalize_trend(raw: Any) -> Optional[TrendItem]:
    """Coerce API / object row into :class:`TrendItem`."""
    if raw is None:
        return None
    if isinstance(raw, TrendItem):
        return raw
    if isinstance(raw, Mapping):
        topic = str(raw.get("topic") or "").strip()
        display = str(raw.get("displayName") or raw.get("display_name") or "").strip()
        category = str(raw.get("category") or "").strip()
        link = str(raw.get("link") or "").strip()
        try:
            post_count = int(raw.get("postCount") or raw.get("post_count") or 0)
        except (TypeError, ValueError):
            post_count = 0
        description = str(raw.get("description") or "").strip()
        status = str(raw.get("status") or "").strip()
    else:
        topic = str(getattr(raw, "topic", "") or "").strip()
        display = str(
            getattr(raw, "display_name", None)
            or getattr(raw, "displayName", None)
            or ""
        ).strip()
        category = str(getattr(raw, "category", "") or "").strip()
        link = str(getattr(raw, "link", "") or "").strip()
        try:
            post_count = int(
                getattr(raw, "post_count", None)
                or getattr(raw, "postCount", None)
                or 0
            )
        except (TypeError, ValueError):
            post_count = 0
        description = str(getattr(raw, "description", "") or "").strip()
        status = str(getattr(raw, "status", "") or "").strip()

    if not topic and not display:
        return None
    feed_uri = feed_uri_from_link(link)
    return TrendItem(
        topic=topic or display,
        display_name=display or topic,
        category=category,
        link=link,
        post_count=post_count,
        feed_uri=feed_uri,
        description=description,
        status=status,
    )


def filter_trends(
    items: Sequence[TrendItem],
    config: TrendsConfig,
) -> List[TrendItem]:
    """Soft niche/safety filter for trends only (not RSS).

    Default config keeps almost the whole top: empty deny/allow lists.
    """
    if not config.enabled:
        return []

    out: List[TrendItem] = []
    for item in items:
        if item.post_count < config.min_post_count:
            continue
        if config.allow_categories:
            cat = (item.category or "").lower()
            if cat not in config.allow_categories:
                continue
        hay = " ".join(
            [
                item.display_name,
                item.topic,
                item.category,
                item.description,
            ]
        ).lower()
        if config.deny_keywords and any(kw in hay for kw in config.deny_keywords):
            continue
        out.append(item)
        if len(out) >= config.max_topics:
            break
    return out


JsonFetcher = Callable[[str], Awaitable[Mapping[str, Any]]]


class BlueSkyTrendingTracker:
    """Live ``getTrends`` with cache; timeline word-count only as API fallback."""

    def __init__(
        self,
        client: Any = None,
        *,
        config: Optional[Mapping[str, Any]] = None,
        fetch_json: Optional[JsonFetcher] = None,
    ) -> None:
        self.client = client
        self.cfg = TrendsConfig.from_mapping(config)
        self._fetch_json = fetch_json
        self.trending_cache: Dict[str, Any] = {}
        self.cache_expiry = timedelta(minutes=self.cfg.cache_minutes)
        self.last_update: Optional[datetime] = None
        self._source: str = "empty"

    def configure(self, config: Optional[Mapping[str, Any]]) -> None:
        """Hot-reload trends knobs (does not clear cache)."""
        self.cfg = TrendsConfig.from_mapping(config)
        self.cache_expiry = timedelta(minutes=self.cfg.cache_minutes)

    def set_fetch_json(self, fetch_json: Optional[JsonFetcher]) -> None:
        self._fetch_json = fetch_json

    def trends_url(self, limit: Optional[int] = None) -> str:
        lim = limit if limit is not None else self.cfg.limit
        lim = max(1, min(int(lim), 25))
        return f"{self.cfg.public_api_base}{GET_TRENDS_PATH}?limit={lim}"

    def feed_url(self, feed_uri: str, *, limit: int = 5) -> str:
        lim = max(1, min(int(limit), 25))
        return (
            f"{self.cfg.public_api_base}{GET_FEED_PATH}"
            f"?feed={quote(feed_uri, safe='')}&limit={lim}"
        )

    def _cache_fresh(self) -> bool:
        return bool(
            self.last_update
            and datetime.now() - self.last_update < self.cache_expiry
            and self.trending_cache.get("items") is not None
        )

    async def _http_get_trends(self, limit: int) -> List[TrendItem]:
        if self._fetch_json is None:
            raise RuntimeError("fetch_json not configured")
        data = await self._fetch_json(self.trends_url(limit))
        raw_list = data.get("trends") if isinstance(data, Mapping) else None
        items: List[TrendItem] = []
        for row in raw_list or []:
            item = normalize_trend(row)
            if item:
                items.append(item)
        return items

    async def _client_get_trends(self, limit: int) -> List[TrendItem]:
        """Prefer typed atproto client when available."""
        if self.client is None:
            raise RuntimeError("no bluesky client")
        unspecced = getattr(getattr(self.client, "app", None), "bsky", None)
        unspecced = getattr(unspecced, "unspecced", None) if unspecced else None
        get_trends = getattr(unspecced, "get_trends", None) if unspecced else None
        if get_trends is None:
            raise AttributeError("app.bsky.unspecced.get_trends unavailable")
        try:
            resp = await get_trends({"limit": limit})
        except TypeError:
            resp = await get_trends(limit=limit)
        raw_list = getattr(resp, "trends", None)
        if raw_list is None and isinstance(resp, Mapping):
            raw_list = resp.get("trends")
        items: List[TrendItem] = []
        for row in raw_list or []:
            item = normalize_trend(row)
            if item:
                items.append(item)
        return items

    async def _timeline_fallback(self, limit: int) -> List[TrendItem]:
        """Legacy word-count from home timeline (API failure only)."""
        if self.client is None:
            return []
        timeline = await self.client.app.bsky.feed.get_timeline({"limit": 100})
        hashtags: List[str] = []
        topics: List[str] = []
        for post in getattr(timeline, "feed", []) or []:
            record = getattr(getattr(post, "post", None), "record", None)
            text = getattr(record, "text", None)
            if not text:
                continue
            hashtags.extend(tag.lower() for tag in re.findall(r"#(\w+)", text))
            topics.extend(w.lower() for w in re.findall(r"\b[A-Za-z]{4,}\b", text))
        hashtag_counts = Counter(hashtags).most_common(limit)
        topic_counts = Counter(topics).most_common(limit)
        items = [
            TrendItem(
                topic=word,
                display_name=word,
                category="timeline",
                link="",
                post_count=count,
            )
            for word, count in topic_counts
        ]
        self.trending_cache["hashtags"] = [
            {"tag": tag, "count": count} for tag, count in hashtag_counts
        ]
        return items

    async def refresh(self, limit: Optional[int] = None) -> List[TrendItem]:
        """Fetch + cache raw trends (pre-filter)."""
        lim = limit if limit is not None else self.cfg.limit
        if not self.cfg.enabled:
            self.trending_cache = {
                "items": [],
                "hashtags": [],
                "timestamp": datetime.now().isoformat(),
            }
            self.last_update = datetime.now()
            self._source = "disabled"
            return []

        items: List[TrendItem] = []
        source = "empty"
        try:
            try:
                items = await self._client_get_trends(lim)
                source = "client"
            except Exception as client_err:
                logger.debug("get_trends via client failed: %s", client_err)
                if self._fetch_json is not None:
                    items = await self._http_get_trends(lim)
                    source = "http"
                else:
                    raise
            if not items:
                raise RuntimeError("getTrends returned empty")
        except Exception as api_err:
            logger.warning(
                "getTrends failed (%s); falling back to timeline word-count",
                api_err,
            )
            try:
                items = await self._timeline_fallback(lim)
                source = "timeline_fallback"
            except Exception as fb_err:
                logger.error("timeline trend fallback failed: %s", fb_err)
                items = []
                source = "empty"

        self.trending_cache = {
            "items": items,
            "hashtags": self.trending_cache.get("hashtags", []),
            "timestamp": datetime.now().isoformat(),
        }
        self.last_update = datetime.now()
        self._source = source
        logger.info(
            "Trends refresh: %s items via %s (cache %sm)",
            len(items),
            source,
            self.cfg.cache_minutes,
        )
        return items

    async def get_raw_trends(self, limit: Optional[int] = None) -> List[TrendItem]:
        if self._cache_fresh():
            return list(self.trending_cache.get("items") or [])
        return await self.refresh(limit)

    async def get_filtered_trends(
        self, limit: Optional[int] = None
    ) -> List[TrendItem]:
        raw = await self.get_raw_trends(limit)
        return filter_trends(raw, self.cfg)

    async def get_trending_topics(self, limit: int = 20) -> List[Dict]:
        """Backward-compatible list of dicts for DynamicContentGenerator."""
        items = await self.get_filtered_trends(limit)
        return [item.as_legacy_dict() for item in items]

    async def get_trending_hashtags(self) -> List[str]:
        await self.get_raw_trends()
        cached = self.trending_cache.get("hashtags") or []
        if cached:
            return [f"#{item['tag']}" for item in cached[:10]]
        # Derive soft tags from live display names when API had no hashtags.
        tags: List[str] = []
        for item in await self.get_filtered_trends():
            for word in re.findall(r"[A-Za-z]{3,}", item.label):
                tag = f"#{word.lower()}"
                if tag not in tags:
                    tags.append(tag)
                if len(tags) >= 10:
                    break
            if len(tags) >= 10:
                break
        return tags or ["#trending", "#discussion", "#thoughts"]

    async def pick_theme_for_posts(self) -> Optional[str]:
        """One display name for TrendingCommentary (None → static fallback)."""
        if not self.cfg.enabled or not self.cfg.use_for_posts:
            return None
        items = await self.get_filtered_trends()
        if not items:
            return None
        import random

        return random.choice(items).label

    @property
    def last_source(self) -> str:
        return self._source


__all__ = [
    "DEFAULT_PUBLIC_API",
    "DEFAULT_TRENDS_CONFIG",
    "BlueSkyTrendingTracker",
    "TrendItem",
    "TrendsConfig",
    "feed_uri_from_link",
    "filter_trends",
    "normalize_trend",
]
