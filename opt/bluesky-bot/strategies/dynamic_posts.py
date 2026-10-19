#!/usr/bin/env python3
"""Dynamic-family post strategies — ADR-001 / STRAT-005.

Extracts former ``AutonomousBlueskyBotV2._create_personal_opinion_post``,
``_create_quality_tip_post``, and ``_create_quality_discussion`` behind
:class:`~post_strategies.PostStrategy` using
:class:`~strategies.ports.DynamicPostsPorts` + :class:`~strategies.image_post.ImagePostHelper`.

Import rules:
- Must not import ``bluesky_bot_v2``.
- Composition root builds ports and registers instances under stable
  config keys in the hybrid registry.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Mapping, Optional

from .image_post import ImagePostHelper
from .ports import DynamicPostsPorts

logger = logging.getLogger(__name__)

# Stable config / learning / A/B / registry keys (do not rename).
PERSONAL_OPINION_STRATEGY_NAME = "_create_personal_opinion_post"
QUALITY_TIP_STRATEGY_NAME = "_create_quality_tip_post"
QUALITY_DISCUSSION_STRATEGY_NAME = "_create_quality_discussion"

# Discussion: 30% question_starter, 70% observation (parity with bot).
_DISCUSSION_QUESTION_RATIO = 0.3


class _DynamicImageStrategy:
    """Shared create path: dynamic_generator → ImagePostHelper → emergency."""

    __slots__ = (
        "_ports",
        "_image",
        "_request_type",
        "_default_topic",
        "_default_content_type",
        "_error_label",
    )

    def __init__(
        self,
        ports: DynamicPostsPorts,
        *,
        request_type: Optional[str],
        default_topic: str,
        default_content_type: str,
        error_label: str,
    ) -> None:
        self._ports = ports
        self._image = ImagePostHelper(ports.image)
        self._request_type = request_type
        self._default_topic = default_topic
        self._default_content_type = default_content_type
        self._error_label = error_label

    def _resolve_request_type(self) -> Optional[str]:
        """Override in subclasses that pick a type at call time."""
        return self._request_type

    async def create(self) -> Any:
        """Produce a dynamic+image post, or emergency on hard failure."""
        try:
            request_type = self._resolve_request_type()
            dynamic_content = await self._ports.dynamic.generate(request_type)

            async def content_creator() -> Mapping[str, Any]:
                return {
                    "post_text": dynamic_content["post_text"],
                    "hashtags": dynamic_content["hashtags"],
                }

            async def fallback_creator() -> Mapping[str, Any]:
                fallback = self._ports.dynamic.fallback()
                return {
                    "post_text": fallback["post_text"],
                    "hashtags": fallback["hashtags"],
                }

            return await self._image.create(
                content_creator,
                dynamic_content.get("topic", self._default_topic),
                dynamic_content.get("content_type", self._default_content_type),
                fallback_creator,
            )
        except Exception as e:
            logger.error("❌ Error in dynamic %s post: %s", self._error_label, e)
            return await self._ports.emergency.create()


class PersonalOpinionStrategy(_DynamicImageStrategy):
    """Personal opinion via ``dynamic_generator`` + image helper."""

    def __init__(self, ports: DynamicPostsPorts) -> None:
        super().__init__(
            ports,
            request_type=None,
            default_topic="personal thoughts",
            default_content_type="personal",
            error_label="personal opinion",
        )


class QualityTipStrategy(_DynamicImageStrategy):
    """Tip-sharing via ``dynamic_generator("tip_sharing")`` + image helper."""

    def __init__(self, ports: DynamicPostsPorts) -> None:
        super().__init__(
            ports,
            request_type="tip_sharing",
            default_topic="useful tips",
            default_content_type="tip",
            error_label="tip",
        )


class QualityDiscussionStrategy(_DynamicImageStrategy):
    """Discussion via question_starter / observation + image helper."""

    def __init__(self, ports: DynamicPostsPorts) -> None:
        super().__init__(
            ports,
            request_type=None,
            default_topic="discussion topic",
            default_content_type="discussion",
            error_label="discussion",
        )

    def _resolve_request_type(self) -> Optional[str]:
        if random.random() < _DISCUSSION_QUESTION_RATIO:
            return "question_starter"
        return "observation"
