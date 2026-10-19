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

- ``upload_image_to_bluesky`` (URL path) — reached only via ``LinkPreviewPort``
- ``clean_html`` / feedparser loop — inside ``fetch_external_content``
- Quality-gate regen flag — owned by content/quality path, not news pick

News item shape expected from ``RssHeadlinesPort`` (dict keys used today):

- ``title`` (str, prefer len > 20)
- ``description`` (truthy required to select)
- ``url`` (str, optional — duplicate + link card)
- ``image_url`` (str, optional — duplicate + thumb)

===========================================================================
Deps inventory: image / theme helpers (STRAT-004)
===========================================================================

| Bot call / field (today)                              | Port / field here                 | Role |
|-------------------------------------------------------|-----------------------------------|------|
| ``formatter.create_post(text, content_type=, …)``     | ``PostFactoryPort`` (shared)      | Text / image post shell |
| ``create_image_prompt_from_text(topic)``              | ``ImagePromptPort.create_prompt`` | LLM visual prompt from topic |
| ``pollinations_ai.generate_image_data(prompt)``       | ``ImageGeneratorPort``            | Bytes from image model |
| ``upload_image_data_to_bluesky(bytes)``               | ``ImageUploadPort.upload``        | ATProto blob for embed |
| ``generate_structured_post_content(prompt, …)``       | ``StructuredContentPort`` (theme) | Theme LLM JSON payload |
| ``_create_post_with_image_generation``                | ``ImagePostHelper`` + ports       | Shared image/fallback glue |
| ``_quality_theme_post``                               | ``ThemePostHelper`` + ports       | Theme pick → image helper |
| ``_create_quality_ai_insight`` (STRAT-006)            | ``ThemePostHelper`` + themes      | AI insight theme family |
| ``_create_quality_list_post`` (STRAT-006)             | ``ThemePostHelper`` + themes      | List theme family |
| ``_create_personal_insight`` (STRAT-008)              | ``ThemePostPorts`` + helper       | Insight themes → image post |
| ``_create_prediction_post`` (STRAT-008)               | ``ThemePostPorts`` + helper       | Prediction themes → image post |

===========================================================================
Deps inventory: dynamic family (STRAT-005)
===========================================================================

| Bot call / field (today)                              | Port / field here                 | Role |
|-------------------------------------------------------|-----------------------------------|------|
| ``dynamic_generator.generate_dynamic_content(…)``     | ``DynamicContentPort.generate``   | Opinion / tip / discussion body |
| ``dynamic_generator._generate_fallback_content()``    | ``DynamicContentPort.fallback``   | Soft miss structured payload |
| ``_create_post_with_image_generation``                | ``ImagePostHelper`` via ports     | Image + formatter glue |
| ``_create_emergency_unique_post``                     | ``FallbackPostPort.create``       | Hard-fail emergency path |

Stable registry / learning keys (do not rename):

- ``_create_personal_opinion_post``
- ``_create_quality_tip_post``
- ``_create_quality_discussion``

===========================================================================
Deps inventory: viral / trending (STRAT-009)
===========================================================================

| Bot call / field (today)                              | Port / field here                 | Role |
|-------------------------------------------------------|-----------------------------------|------|
| ``engagement_optimizer.generate_viral_post_prompts``  | ``ViralPromptsPort.generate``     | Side-effect parity (list unused in prompt today) |
| ``generate_structured_post_content(prompt, …)``       | ``StructuredContentPort``         | LLM JSON post_text + hashtags |
| ``_create_post_with_image_generation``                | ``ImagePostHelper`` via ports     | Image + formatter glue |
| theme/topic random lists                              | strategy module constants         | hot-take / trending themes |

Stable registry / learning keys (do not rename):

- ``_create_viral_hot_take``
- ``_create_trending_commentary``

===========================================================================
Deps inventory: soft-fail helpers (SOFT-001)
===========================================================================

| Bot call / field (today)                              | Port / field here                 | Role |
|-------------------------------------------------------|-----------------------------------|------|
| ``generate_structured_post_content``                  | ``StructuredContentPort``         | Motivational / emergency LLM JSON |
| ``_create_post_with_image_generation``                | ``ImagePostHelper`` / Theme ports | Image + formatter glue |
| ``_is_duplicate_content``                             | ``DuplicateContentPort``          | Fallback chain uniqueness |
| ``_create_emergency_unique_post``                     | ``FallbackPostPort``              | Terminal emergency path |
| registry ``resolve`` / getattr                        | ``StrategyLookupPort``            | Fallback chain strategy pick |

Stable names (do not rename):

- ``_create_motivational_moment_post``
- ``_create_emergency_unique_post``

``_create_fallback_post_for_duplicate`` is a helper (not a weighted strategy key).

STATE-001 (this orch): content dedup/publish façade — not heartbeat/cache sync.

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
    Dict,
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
    """Build a post object from final text (optional image blob embed)."""

    def create_post(
        self,
        text: str,
        *,
        content_type: str = "news",
        image_blob: Optional[Any] = None,
        image_alt_text: Optional[str] = None,
    ) -> Any: ...


@dataclass
class CallablePostFactory:
    """Binds ``formatter.create_post``-shaped callable."""

    _create_post: Callable[..., Any]

    def create_post(
        self,
        text: str,
        *,
        content_type: str = "news",
        image_blob: Optional[Any] = None,
        image_alt_text: Optional[str] = None,
    ) -> Any:
        kwargs: Dict[str, Any] = {"content_type": content_type}
        if image_blob is not None:
            kwargs["image_blob"] = image_blob
        if image_alt_text is not None:
            kwargs["image_alt_text"] = image_alt_text
        return self._create_post(text, **kwargs)


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


# --- Image generation / upload (STRAT-004) ---


@runtime_checkable
class ImagePromptPort(Protocol):
    """Turn a topic/text into a visual generation prompt."""

    async def create_prompt(self, text: str) -> str: ...


@dataclass
class CallableImagePrompt:
    """Binds ``create_image_prompt_from_text``-shaped callable."""

    _create: Callable[[str], Awaitable[str]]

    async def create_prompt(self, text: str) -> str:
        return await self._create(text)


@runtime_checkable
class ImageGeneratorPort(Protocol):
    """Generate raw image bytes from a visual prompt (e.g. Pollinations)."""

    async def generate_image_data(self, prompt: str) -> Optional[bytes]: ...


@dataclass
class CallableImageGenerator:
    """Binds ``pollinations_ai.generate_image_data``-shaped callable."""

    _generate: Callable[[str], Awaitable[Optional[bytes]]]

    async def generate_image_data(self, prompt: str) -> Optional[bytes]:
        return await self._generate(prompt)


@runtime_checkable
class ImageUploadPort(Protocol):
    """Upload image bytes to BlueSky; returns blob handle or ``None``."""

    async def upload(self, image_data: bytes) -> Optional[Any]: ...


@dataclass
class CallableImageUpload:
    """Binds ``upload_image_data_to_bluesky``-shaped callable."""

    _upload: Callable[[bytes], Awaitable[Optional[Any]]]

    async def upload(self, image_data: bytes) -> Optional[Any]:
        return await self._upload(image_data)


@dataclass
class ImagePostPorts:
    """Dependencies for :class:`~strategies.image_post.ImagePostHelper`.

    Bot (composition root) builds one instance and injects it; strategy /
    helper modules must not import ``bluesky_bot_v2``.
    """

    posts: PostFactoryPort
    image_prompt: ImagePromptPort
    image_gen: ImageGeneratorPort
    image_upload: ImageUploadPort


@dataclass
class ThemePostPorts:
    """Dependencies for :class:`~strategies.image_post.ThemePostHelper`.

    Theme pick → structured LLM → shared image-post path (STRAT-004 / STRAT-006).
    """

    content: StructuredContentPort
    image: ImagePostPorts


# --- Poll factory (STRAT-007) ---
#
# | Bot call / field (today)                         | Port / field here              | Role |
# |--------------------------------------------------|--------------------------------|------|
# | ``generate_structured_post_content(prompt, …)``  | ``StructuredContentPort``      | LLM intro + hashtags |
# | ``formatter.create_poll(question=, options=, …)``| ``PollFactoryPort.create_poll``| Poll RichTextPost shell |


@runtime_checkable
class PollFactoryPort(Protocol):
    """Build a poll post from question text and option labels."""

    def create_poll(
        self,
        *,
        question: str,
        options: Sequence[str],
        duration_hours: int = 24,
        content_type: str = "poll",
    ) -> Any: ...


@dataclass
class CallablePollFactory:
    """Binds ``formatter.create_poll``-shaped callable."""

    _create_poll: Callable[..., Any]

    def create_poll(
        self,
        *,
        question: str,
        options: Sequence[str],
        duration_hours: int = 24,
        content_type: str = "poll",
    ) -> Any:
        return self._create_poll(
            question=question,
            options=list(options),
            duration_hours=duration_hours,
            content_type=content_type,
        )


@dataclass
class PollStrategyPorts:
    """Dependencies for :class:`~strategies.poll_post.QualityPollStrategy`.

    Bot (composition root) builds one instance and injects it; strategy
    modules must not import ``bluesky_bot_v2``.
    """

    content: StructuredContentPort
    poll: PollFactoryPort


# --- Dynamic content generator (STRAT-005) ---


@runtime_checkable
class DynamicContentPort(Protocol):
    """Audience-weighted dynamic post text + hashtags (and soft fallback)."""

    async def generate(
        self, content_type: Optional[str] = None
    ) -> Mapping[str, Any]:
        """Return dict with at least ``post_text`` / ``hashtags`` (optional topic)."""
        ...

    def fallback(self) -> Mapping[str, Any]:
        """Safe structured payload when primary dynamic path soft-fails."""
        ...


@dataclass
class CallableDynamicContent:
    """Binds ``DynamicContentGenerator.generate_dynamic_content`` + fallback."""

    _generate: Callable[..., Awaitable[Mapping[str, Any]]]
    _fallback: Callable[[], Mapping[str, Any]]

    async def generate(
        self, content_type: Optional[str] = None
    ) -> Mapping[str, Any]:
        if content_type is None:
            return await self._generate()
        return await self._generate(content_type)

    def fallback(self) -> Mapping[str, Any]:
        return self._fallback()


@dataclass
class DynamicPostsPorts:
    """Dependencies for opinion / tip / discussion strategies (STRAT-005).

    Bot (composition root) builds one instance and injects it; strategy modules
    must not import ``bluesky_bot_v2``.
    """

    dynamic: DynamicContentPort
    image: ImagePostPorts
    emergency: FallbackPostPort


# --- Viral prompts (STRAT-009 / STRAT-010) ---


@runtime_checkable
class ViralPromptsPort(Protocol):
    """Produce viral-style prompt templates (engagement optimizer parity)."""

    def generate(self) -> Sequence[str]:
        """Return prompt strings (may be unused by the hot-take body today)."""
        ...


@dataclass
class CallableViralPrompts:
    """Binds ``EngagementOptimizer.generate_viral_post_prompts``-shaped callable."""

    _generate: Callable[[], Sequence[str]]

    def generate(self) -> Sequence[str]:
        return self._generate()


@dataclass
class ViralPostsPorts:
    """Dependencies for viral hot-take / trending commentary (STRAT-010).

    Bot (composition root) builds one instance and injects it; strategy modules
    must not import ``bluesky_bot_v2``.

    ``pick_trending_theme`` — optional live «Актуальные» label; ``None``/empty
    falls back to static ``TRENDING_THEMES``.
    """

    content: StructuredContentPort
    image: ImagePostPorts
    viral_prompts: ViralPromptsPort
    pick_trending_theme: Optional[Callable[[], Awaitable[Optional[str]]]] = None


# --- Soft-fail / duplicate fallback (SOFT-001…003) ---


@runtime_checkable
class StrategyLookupPort(Protocol):
    """Resolve a stable strategy key to an async zero-arg post creator."""

    def lookup(self, name: str) -> Optional[Callable[[], Awaitable[Any]]]:
        """Return awaitable factory, or ``None`` if unavailable."""
        ...


@dataclass
class CallableStrategyLookup:
    """Binds registry resolve + optional getattr-style fallback."""

    _lookup: Callable[[str], Optional[Callable[[], Awaitable[Any]]]]

    def lookup(self, name: str) -> Optional[Callable[[], Awaitable[Any]]]:
        return self._lookup(name)


@dataclass
class SoftFailPorts:
    """Dependencies for motivational / emergency soft-fail strategies.

    Reuses theme structured + image path (ThemePostPorts shape).
    """

    content: StructuredContentPort
    image: ImagePostPorts


@dataclass
class DuplicateFallbackPorts:
    """Dependencies for duplicate-replacement fallback chain (SOFT-003)."""

    lookup: StrategyLookupPort
    duplicates: DuplicateContentPort
    emergency: FallbackPostPort
