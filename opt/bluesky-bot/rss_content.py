#!/usr/bin/env python3
"""RSS external content fetch — thin-shell RSS-001.

Extracts former ``fetch_external_content`` plus image extraction,
entry priority, and RSS dedupe helpers.

Import rules:
- Must not import ``bluesky_bot_v2``.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime
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

import feedparser

from url_safety import UnsafeURLError, validate_outbound_url

logger = logging.getLogger(__name__)


def clean_html(raw_html: str) -> str:
    """Strip HTML tags / entities (parity with bot ``clean_html``)."""
    if not raw_html:
        return ""
    import html as html_mod

    text = html_mod.unescape(raw_html)
    clean_text = re.sub(r"<[^>]+>", "", text)
    clean_text = re.sub(r"submitted by /u/[\w-]+", "", clean_text)
    clean_text = re.sub(r"\[link\]|\[comments\]", "", clean_text)
    return clean_text.strip()


def enhanced_image_extraction(entry: Any) -> Optional[str]:
    """Best-effort image URL from a feedparser entry."""
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url")

    if hasattr(entry, "enclosures"):
        for enclosure in entry.enclosures:
            if enclosure.get("type", "").startswith("image/"):
                return enclosure.get("href")

    if hasattr(entry, "media_content"):
        for media in entry.media_content:
            if media.get("type", "").startswith("image/"):
                return media.get("url")

    content_fields: List[str] = []
    if hasattr(entry, "content"):
        content_fields.extend([c.get("value", "") for c in entry.content])
    if hasattr(entry, "summary"):
        content_fields.append(entry.summary)

    for content in content_fields:
        img_patterns = [
            r'<img[^>]+src=["\']([^"\']+)["\']',
            r"<img[^>]+src=([^>\s]+)",
            r'data-src=["\']([^"\']+)["\']',
        ]
        for pattern in img_patterns:
            img_match = re.search(pattern, content)
            if img_match:
                return img_match.group(1)

    if hasattr(entry, "links"):
        for link in entry.links:
            if link.get("type", "").startswith("image/"):
                return link.get("href")

    return None


def calculate_entry_priority(entry_data: Mapping[str, Any], source_url: str) -> float:
    """Rank score for an RSS entry."""
    score = 0.0

    if "venturebeat.com" in source_url or "techcrunch.com" in source_url:
        score += 0.25
    elif "ycombinator.com" in source_url or "reddit.com" in source_url:
        score += 0.2
    else:
        score += 0.15

    if entry_data.get("image_url"):
        score += 0.2

    title_len = len(entry_data.get("title", "") or "")
    if 40 <= title_len <= 120:
        score += 0.15
    elif title_len > 120:
        score += 0.05

    desc_len = len(entry_data.get("description", "") or "")
    if desc_len > 80:
        score += 0.1

    if entry_data.get("published"):
        try:
            published_time = time.mktime(
                time.strptime(str(entry_data["published"])[:25], "%a, %d %b %Y %H:%M:%S")
            )
            age_hours = (time.time() - published_time) / 3600
            if age_hours < 24:
                score += 0.1
            elif age_hours < 168:
                score += 0.05
        except Exception:
            pass

    fetch_time = entry_data.get("fetch_time", 1)
    if fetch_time > 3:
        score *= 0.9

    return round(score, 3)


def deduplicate_rss_entries(entries: Sequence[Mapping[str, Any]]) -> List[Dict]:
    """Drop URL duplicates and near-duplicate titles (Jaccard > 0.65)."""
    seen_urls: set = set()
    seen_titles: set = set()
    unique_entries: List[Dict] = []

    for entry in entries:
        url = entry.get("url", "") or ""
        title = (entry.get("title", "") or "").lower().strip()

        if url and url in seen_urls:
            logger.debug("🔄 Дубликат URL: %s...", url[:50])
            continue

        title_words = set(title.split())
        is_similar = False
        for seen_title in seen_titles:
            seen_words = set(seen_title.split())
            if title_words and seen_words:
                intersection = len(title_words.intersection(seen_words))
                union = len(title_words.union(seen_words))
                similarity = intersection / union if union > 0 else 0
                if similarity > 0.65:
                    is_similar = True
                    logger.debug(
                        "🔄 Похожий заголовок: %s... (схожесть: %.2f)",
                        title[:50],
                        similarity,
                    )
                    break

        if not is_similar and title:
            unique_entries.append(dict(entry))
            seen_urls.add(url)
            seen_titles.add(title)

    return unique_entries


@dataclass
class RssContentPorts:
    """Dependencies for :class:`RssContentFetcher`."""

    http_get_text: Callable[..., Awaitable[tuple]]
    record_fetch: Callable[..., None]
    set_trend_headlines: Callable[[Sequence[str]], None]
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    clean: Callable[[str], str] = clean_html


class RssContentFetcher:
    """Fetch / rank / dedupe RSS headlines for news strategies."""

    __slots__ = ("_ports",)

    def __init__(self, ports: RssContentPorts) -> None:
        self._ports = ports

    async def fetch(
        self,
        feed_urls: Sequence[str],
        *,
        max_sources: int = 6,
        target_entries: int = 15,
        entries_per_source: int = 4,
        final_limit: int = 10,
    ) -> List[Dict]:
        ports = self._ports
        all_entries: List[Dict] = []
        available_sources = list(feed_urls)
        random.shuffle(available_sources)

        sources_used = 0
        logger.info(
            "🌐 Начинаем получение RSS из %s доступных источников...",
            len(available_sources),
        )

        for feed_url in available_sources:
            if sources_used >= max_sources or len(all_entries) >= target_entries:
                break
            try:
                try:
                    feed_url = validate_outbound_url(feed_url)
                except UnsafeURLError as e:
                    logger.warning("⚠️ Unsafe RSS URL skipped: %s", e)
                    continue

                timeout = 20 if "cnn.com" in feed_url else 15
                start_time = datetime.now()
                status, content = await ports.http_get_text(
                    feed_url, timeout=timeout
                )
                if status != 200:
                    logger.warning("⚠️ %s: HTTP %s", feed_url, status)
                    continue

                feed = feedparser.parse(content)
                fetch_time = (datetime.now() - start_time).total_seconds()
                source_entries: List[Dict] = []

                for entry in feed.entries[:entries_per_source]:
                    entry_data = {
                        "title": ports.clean(entry.title),
                        "url": entry.link,
                        "description": ports.clean(entry.get("summary", "")[:250]),
                        "source": (
                            ports.clean(feed.feed.title)
                            if hasattr(feed.feed, "title")
                            else "Unknown"
                        ),
                        "published": entry.get("published", ""),
                        "fetch_time": fetch_time,
                        "source_url": feed_url,
                        "image_url": None,
                        "priority_score": 0,
                    }
                    entry_data["image_url"] = enhanced_image_extraction(entry)
                    entry_data["priority_score"] = calculate_entry_priority(
                        entry_data, feed_url
                    )
                    if len(entry_data["title"]) > 20 and entry_data["title"] != "Unknown":
                        source_entries.append(entry_data)

                if source_entries:
                    all_entries.extend(source_entries)
                    sources_used += 1
                    source_name = (
                        feed.feed.title
                        if hasattr(feed.feed, "title")
                        else feed_url.split("//")[-1].split("/")[0]
                    )
                    logger.info(
                        "✅ %s: %s записей за %.1fс",
                        source_name,
                        len(source_entries),
                        fetch_time,
                    )
                    try:
                        ports.record_fetch(
                            feed_url,
                            success=True,
                            latency=fetch_time,
                            entries=len(source_entries),
                            duplicates=entries_per_source - len(source_entries),
                        )
                    except Exception:
                        pass
                else:
                    try:
                        ports.record_fetch(
                            feed_url, success=False, latency=fetch_time
                        )
                    except Exception:
                        pass

                await ports.sleep(0.3)

            except asyncio.TimeoutError:
                source_name = feed_url.split("//")[-1].split("/")[0]
                logger.warning("⏰ %s: таймаут (%sс)", source_name, timeout)
                try:
                    ports.record_fetch(
                        feed_url, success=False, latency=float(timeout)
                    )
                except Exception:
                    pass
                continue
            except Exception as e:
                source_name = feed_url.split("//")[-1].split("/")[0]
                logger.warning("❌ %s: %s...", source_name, str(e)[:80])
                try:
                    ports.record_fetch(feed_url, success=False, latency=0.0)
                except Exception:
                    pass
                continue

        unique_entries = deduplicate_rss_entries(all_entries)
        prioritized_entries = sorted(
            unique_entries, key=lambda x: x.get("priority_score", 0), reverse=True
        )

        with_images = sum(1 for e in prioritized_entries if e.get("image_url"))
        avg_fetch_time = (
            sum(e.get("fetch_time", 0) for e in prioritized_entries)
            / len(prioritized_entries)
            if prioritized_entries
            else 0
        )

        logger.info("📊 RSS аналитика:")
        logger.info(
            "   🌐 Обработано источников: %s/%s",
            sources_used,
            len(available_sources),
        )
        logger.info(
            "   📰 Всего записей: %s → уникальных: %s",
            len(all_entries),
            len(unique_entries),
        )
        logger.info(
            "   🖼️ С изображениями: %s/%s", with_images, len(prioritized_entries)
        )
        logger.info("   ⚡ Среднее время загрузки: %.1fс", avg_fetch_time)

        final_entries = prioritized_entries[:final_limit]
        logger.info(
            "📋 Выбрано %s лучших записей для использования", len(final_entries)
        )
        ports.set_trend_headlines(
            [e.get("title", "") for e in prioritized_entries[:30]]
        )
        return final_entries
