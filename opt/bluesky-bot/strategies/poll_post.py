#!/usr/bin/env python3
"""Quality poll post strategy — ADR-001 / STRAT-007.

Implements the former ``AutonomousBlueskyBotV2._create_quality_poll_post``
flow behind :class:`~post_strategies.PostStrategy` using
:class:`~strategies.ports.PollStrategyPorts` only.

Import rules:
- Must not import ``bluesky_bot_v2``.
- Composition root builds ports and registers this instance under
  ``STRATEGY_NAME`` (``_create_quality_poll_post``) in the hybrid registry.
"""

from __future__ import annotations

import logging
import random
from typing import Any, Mapping, Sequence, Tuple

from .ports import PollStrategyPorts

logger = logging.getLogger(__name__)

# Stable config / learning / A/B / registry key (do not rename).
STRATEGY_NAME = "_create_quality_poll_post"

# Topic → option labels (parity with bot).
POLL_TOPICS: Sequence[Tuple[str, Sequence[str]]] = (
    ("tabs vs spaces", ("Табы", "Пробелы")),
    ("light vs dark theme", ("Светлая тема", "Темная тема")),
    ("framework choice: React vs Vue", ("React", "Vue")),
    ("preferred OS: Windows vs Linux", ("Windows", "Linux")),
)

_DEFAULT_DURATION_HOURS = 24
_FALLBACK_CONTENT: Mapping[str, str] = {
    "post_text": "Время для вашего мнения! Что вы думаете по этому поводу?",
    "hashtags": "#опрос #мнение #IT",
}


class QualityPollStrategy:
    """Poll family strategy: topic pick → LLM intro → formatter.create_poll.

    Satisfies ``post_strategies.PostStrategy`` structurally (``async create``).
    """

    __slots__ = ("_ports",)

    def __init__(self, ports: PollStrategyPorts) -> None:
        self._ports = ports

    async def create(self) -> Any:
        """Produce a poll post (structured intro + options / duration)."""
        selected_topic, poll_options = random.choice(list(POLL_TOPICS))
        structured_content = await self._ports.content.generate(
            _build_poll_prompt(selected_topic),
            model_key="creative",
        )
        if not structured_content:
            structured_content = dict(_FALLBACK_CONTENT)

        post_text = structured_content.get("post_text", "")
        hashtags = structured_content.get("hashtags", "")
        final_post_text = f"{post_text}\n\n{hashtags}".strip()

        logger.info("📊 Создание опроса на тему: %s", selected_topic)
        return self._ports.poll.create_poll(
            question=final_post_text,
            options=list(poll_options),
            duration_hours=_DEFAULT_DURATION_HOURS,
            content_type="poll",
        )


def _build_poll_prompt(selected_topic: str) -> str:
    return f"""
            Create a poll post about "{selected_topic}".
            Provide the output in JSON format. "post_text" (in English, ~150 chars) should introduce the poll. "hashtags" should be 3-4 relevant tags. The poll options will be added separately.

            Example for "tabs vs spaces":
            {{
              "post_text": "Вечный бой, который не утихает... Что выбираете вы для форматирования кода? Голосуйте! 💻",
              "hashtags": "#холивар #код #программирование #опрос"
            }}
            """
