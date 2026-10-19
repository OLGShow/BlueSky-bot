#!/usr/bin/env python3
"""News/RSS strategy ports (Protocols) for DIP — ADR-001 / STRAT-001.

Inventory of ``AutonomousBlueskyBotV2._create_quality_news_post`` (today)
and the narrow deps the extracted news strategy will need (STRAT-002).
The bot remains the composition root; strategies never see the bot class.

Strategy contract stays in ``post_strategies.PostStrategy`` (not re-exported
here — avoids coupling this package to registry helpers beyond ports).

===========================================================================
Deps inventory: bot today → ports surface
===========================================================================

| Bot call / field (today)                         | Port / field here              | Role |
|--------------------------------------------------|--------------------------------|------|
| ``fetch_external_content()``                     | ``RssHeadlinesPort.fetch``     | RSS headlines list |
| ``self.rss_feeds`` (log on empty RSS)            | ``RssFeedsPort.urls``          | Diagnostic feed list |
| ``_is_duplicate_content(text, url, image_url)``  | ``DuplicateContentPort``       | Skip already-published news |
| ``generate_structured_post_content(prompt, …)``  | ``StructuredContentPort``      | LLM JSON post_text + hashtags |
| ``formatter.create_post(text, content_type=…)``  | ``PostFactoryPort.create_post``| Plain RichTextPost shell |
| ``create_post_with_link_preview(…)``             | ``LinkPreviewPort``            | Link card + optional image |
| ``_create_personal_opinion_post()``              | ``FallbackPostPort.create``    | Soft miss / error fallback |

Private helpers **not** moved into this surface (stay on bot / other
strategies until a later family extract):

- ``_create_post_with_image_generation`` — used by opinion fallback, not
  news happy-path directly
- ``upload_image_to_bluesky`` — reached only via ``LinkPreviewPort``
- ``clean_html`` / feedparser loop — inside ``fetch_external_content``
- Quality-gate regen flag — owned by content/quality path, not news pick

News item shape expected from ``RssHeadlinesPort`` (dict keys used today):

- ``title`` (str, prefer len > 20)
- ``description`` (truthy required to select)
- ``url`` (str, optional — duplicate + link card)
- ``image_url`` (str, optional — duplicate + thumb)

Import rules (ADR invariants):
- This module must not import ``bluesky_bot_v2`` or application services.
- Stdlib / typing only — keeps the strategies → bot edge acyclic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Any,
    Awaitable,
    Callable,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    runtime_checkable,
)

# Loose news-item mapping (title/description/url/image_url). Strategies
# treat missing keys as empty via ``.get`` — same as today's bot loop.
NewsItem = Mapping[str, Any]


# --- RSS headlines ---


@runtime_checkable
class RssHeadlinesPort(Protocol):
    """Fetch external/RSS headline candidates for a news post."""

    async def fetch(self) -> Sequence[NewsItem]:
        """Return headline dicts (may be empty on soft miss)."""
        ...


@dataclass
class CallableRssHeadlines:
    """Binds an async zero-arg fetch callable (composition root / fakes)."""

    _fetch: Callable[[], Awaitable[Sequence[NewsItem]]]

    async def fetch(self) -> Sequence[NewsItem]:
        return await self._fetch()


# --- RSS feed list (diagnostics only) ---


@runtime_checkable
class RssFeedsPort(Protocol):
    """Read-only list of configured RSS feed URLs (logging / diagnostics)."""

    @property
    def urls(self) -> Sequence[str]: ...


@dataclass(frozen=True)
class RssFeedsView:
    """Static snapshot of feed URLs."""

    urls: Sequence[str] = ()


@dataclass
class LiveRssFeeds:
    """Re-resolves feed URLs on each access (bot may refresh ``rss_feeds``)."""

    _get_urls: Callable[[], Sequence[str]]

    @property
    def urls(self) -> Sequence[str]:
        return self._get_urls()


# --- Duplicate gate ---


@runtime_checkable
class DuplicateContentPort(Protocol):
    """True when text/url/image was already published (or too similar)."""

    def is_duplicate(
        self,
        text: str,
        url: Optional[str] = None,
        image_url: Optional[str] = None,
    ) -> bool: ...


@dataclass
class CallableDuplicateContent:
    """Binds ``_is_duplicate_content``-shaped callable."""

    _is_duplicate: Callable[..., bool]

    def is_duplicate(
        self,
        text: str,
        url: Optional[str] = None,
        image_url: Optional[str] = None,
    ) -> bool:
        return self._is_duplicate(text, url, image_url)


# --- Structured LLM content ---


@runtime_checkable
class StructuredContentPort(Protocol):
    """Generate structured post payload (``post_text`` + ``hashtags``)."""

    async def generate(
        self, prompt: str, *, model_key: str = "creative"
    ) -> Optional[Mapping[str, str]]: ...


@dataclass
class CallableStructuredContent:
    """Binds ``generate_structured_post_content``-shaped callable."""

    _generate: Callable[..., Awaitable[Optional[Mapping[str, str]]]]

    async def generate(
        self, prompt: str, *, model_key: str = "creative"
    ) -> Optional[Mapping[str, str]]:
        return await self._generate(prompt, model_key=model_key)


# --- Plain post factory (formatter) ---


@runtime_checkable
class PostFactoryPort(Protocol):
    """Build a plain post object (no embed) from final text."""

    def create_post(self, text: str, *, content_type: str = "news") -> Any: ...


@dataclass
class CallablePostFactory:
    """Binds ``formatter.create_post``-shaped callable."""

    _create_post: Callable[..., Any]

    def create_post(self, text: str, *, content_type: str = "news") -> Any:
        return self._create_post(text, content_type=content_type)


# --- Link preview + image ---


@runtime_checkable
class LinkPreviewPort(Protocol):
    """Build a post with external link card and optional image thumb."""

    async def create_with_preview(
        self,
        text: str,
        url: str,
        title: str,
        description: str,
        image_url: Optional[str] = None,
    ) -> Any: ...


@dataclass
class CallableLinkPreview:
    """Binds ``create_post_with_link_preview``-shaped callable."""

    _create: Callable[..., Awaitable[Any]]

    async def create_with_preview(
        self,
        text: str,
        url: str,
        title: str,
        description: str,
        image_url: Optional[str] = None,
    ) -> Any:
        return await self._create(text, url, title, description, image_url)


# --- Fallback post (opinion / soft miss) ---


@runtime_checkable
class FallbackPostPort(Protocol):
    """Produce an alternate post when news path soft-fails."""

    async def create(self) -> Any: ...


@dataclass
class CallableFallbackPost:
    """Binds ``_create_personal_opinion_post``-shaped callable."""

    _create: Callable[[], Awaitable[Any]]

    async def create(self) -> Any:
        return await self._create()


# --- Composition bundle (STRAT-002 injection shape) ---


@dataclass
class NewsStrategyPorts:
    """All dependencies the news/RSS ``PostStrategy`` will take (STRAT-002).

    Bot (composition root) builds one instance from its fields/methods and
    injects it; the strategy module must not import ``bluesky_bot_v2``.
    """

    headlines: RssHeadlinesPort
    feeds: RssFeedsPort
    duplicates: DuplicateContentPort
    content: StructuredContentPort
    posts: PostFactoryPort
    link_preview: LinkPreviewPort
    fallback: FallbackPostPort
