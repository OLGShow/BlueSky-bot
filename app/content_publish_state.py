#!/usr/bin/env python3
"""Content dedup / publish marking façade — Phase 7 / STATE-001.

Extracts hash, Jaccard similarity, duplicate checks, mark-published pruning,
and hash cleanup from ``AutonomousBlueskyBotV2``.

Import rules:
- Must not import ``bluesky_bot_v2``.
- Operates on an injected memory object with publish-set fields.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Mapping, MutableSet, Optional, Sequence

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.8
PUBLISH_SET_SOFT_CAP = 500
PUBLISH_SET_KEEP = 400
HASH_LOOKBACK_DAYS = 30

# Align with bot ``_cleanup_old_content_hashes`` retention map.
MEMORY_LIST_RETENTION: Mapping[str, int] = {
    "successful_posts": 500,
    "failed_posts": 200,
    "repost_performance": 200,
    "viral_posts": 100,
    "pattern_blacklist": 50,
}


def generate_content_hash(
    text: str, url: Optional[str] = None, image_url: Optional[str] = None
) -> str:
    """MD5 of normalized text + optional url/image_url parts."""
    content_parts = [text.lower().strip()]
    if url:
        content_parts.append(url)
    if image_url:
        content_parts.append(image_url)
    content_string = "|".join(content_parts)
    return hashlib.md5(
        content_string.encode("utf-8"), usedforsecurity=False
    ).hexdigest()


def calculate_text_similarity(text1: str, text2: str) -> float:
    """Jaccard similarity on cleaned word sets (hashtags/emoji stripped)."""
    clean_text1 = re.sub(r"[#@][\w]+|[^\w\s]", "", text1.lower()).strip()
    clean_text2 = re.sub(r"[#@][\w]+|[^\w\s]", "", text2.lower()).strip()

    if not clean_text1 or not clean_text2:
        return 0.0

    words1 = set(clean_text1.split())
    words2 = set(clean_text2.split())

    if not words1 or not words2:
        return 0.0

    intersection = len(words1.intersection(words2))
    union = len(words1.union(words2))
    return intersection / union if union > 0 else 0.0


def _prune_set(values: MutableSet[str], soft_cap: int, keep: int) -> MutableSet[str]:
    if len(values) <= soft_cap:
        return values
    return set(list(values)[-keep:])


class ContentPublishState:
    """Dedup + publish marking over bot memory publish fields."""

    __slots__ = ("_memory",)

    def __init__(self, memory: Any) -> None:
        self._memory = memory

    def generate_content_hash(
        self,
        text: str,
        url: Optional[str] = None,
        image_url: Optional[str] = None,
    ) -> str:
        return generate_content_hash(text, url, image_url)

    def calculate_text_similarity(self, text1: str, text2: str) -> float:
        return calculate_text_similarity(text1, text2)

    def is_duplicate(
        self,
        text: str,
        url: Optional[str] = None,
        image_url: Optional[str] = None,
        *,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
        recent_limit: int = 20,
    ) -> bool:
        """True when hash/URL hit or recent text similarity exceeds threshold."""
        memory = self._memory
        content_hash = generate_content_hash(text, url, image_url)

        if content_hash in memory.published_content_hashes:
            logger.info(
                "🔄 Найден дубликат по хешу контента: %s...", content_hash[:8]
            )
            return True

        if url and url in memory.published_urls:
            logger.info("🔄 Найден дубликат по URL: %s...", url[:50])
            return True

        recent_posts: Sequence[Any] = (
            memory.successful_posts[-recent_limit:]
            if memory.successful_posts
            else []
        )
        for post in recent_posts:
            if "text" in post:
                similarity = calculate_text_similarity(text, post["text"])
                if similarity > similarity_threshold:
                    logger.info(
                        "🔄 Найден дубликат по схожести текста: %.2f", similarity
                    )
                    return True

        return False

    def mark_published(
        self,
        text: str,
        url: Optional[str] = None,
        image_url: Optional[str] = None,
        *,
        soft_cap: int = PUBLISH_SET_SOFT_CAP,
        keep: int = PUBLISH_SET_KEEP,
    ) -> str:
        """Mark content published; prune sets past soft_cap. Returns hash."""
        memory = self._memory
        content_hash = generate_content_hash(text, url, image_url)
        memory.published_content_hashes.add(content_hash)

        if url:
            memory.published_urls.add(url)

        memory.published_content_hashes = _prune_set(
            memory.published_content_hashes, soft_cap, keep
        )
        memory.published_urls = _prune_set(
            memory.published_urls, soft_cap, keep
        )

        logger.debug(
            "📝 Контент отмечен как опубликованный: %s...", content_hash[:8]
        )
        return content_hash

    def cleanup_old_hashes(
        self,
        *,
        lookback_days: int = HASH_LOOKBACK_DAYS,
        now: Optional[datetime] = None,
        retention: Optional[Mapping[str, int]] = None,
    ) -> None:
        """Rebuild publish sets from recent successful posts; trim memory lists."""
        memory = self._memory
        clock = now or datetime.now()
        cutoff_date = clock - timedelta(days=lookback_days)

        recent_hashes: set = set()
        recent_urls: set = set()

        for post in memory.successful_posts or []:
            if not post.get("timestamp"):
                continue
            try:
                post_date = (
                    datetime.fromisoformat(post["timestamp"])
                    if isinstance(post["timestamp"], str)
                    else post["timestamp"]
                )
                if post_date > cutoff_date:
                    if "content_hash" in post:
                        recent_hashes.add(post["content_hash"])
                    if "url" in post:
                        recent_urls.add(post["url"])
            except Exception:
                pass

        old_hash_count = len(memory.published_content_hashes)
        old_url_count = len(memory.published_urls)
        memory.published_content_hashes = recent_hashes
        memory.published_urls = recent_urls
        logger.info(
            "🧹 Хеши: %s->%s, URLs: %s->%s",
            old_hash_count,
            len(recent_hashes),
            old_url_count,
            len(recent_urls),
        )

        limits = retention or MEMORY_LIST_RETENTION
        for attr, limit in limits.items():
            lst = getattr(memory, attr, None)
            if lst is not None and isinstance(lst, list) and len(lst) > limit:
                old_len = len(lst)
                setattr(memory, attr, lst[-limit:])
                logger.info("🧹 Retention %s: %s->%s", attr, old_len, limit)
