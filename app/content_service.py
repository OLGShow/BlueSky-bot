#!/usr/bin/env python3
"""
ContentService — extracted content helpers to decouple orchestration.

Depends only on ContentPorts (ADR-001 / CONT-003). Must not import
bluesky_bot_v2; the bot remains the composition root that builds ports.
"""

from __future__ import annotations

import unicodedata
from typing import List, Optional

from content_ports import ContentPorts

# Bluesky app.bsky.feed.post text limit (~300 Unicode grapheme clusters).
BLUESKY_MAX_GRAPHEMES = 300


class OutboundContentError(ValueError):
    """Outbound text rejected at the publish/comment boundary."""


def split_graphemes(text: str) -> List[str]:
    """Approximate grapheme clusters without external deps.

    Stricter than real EGC (ZWJ-emoji counted in parts) — safer for the
    Bluesky 300-grapheme limit.
    """
    if not text:
        return []
    text = unicodedata.normalize('NFC', text)
    clusters: List[str] = []
    buf = ''
    for ch in text:
        if buf and unicodedata.combining(ch):
            buf += ch
        else:
            if buf:
                clusters.append(buf)
            buf = ch
    if buf:
        clusters.append(buf)
    return clusters


def sanitize_outbound_text(text: str) -> str:
    """Strip NUL / C0 / C1 control characters; keep newlines and tabs."""
    if not text:
        return ''
    out: List[str] = []
    for ch in text:
        code = ord(ch)
        if ch in ('\n', '\t'):
            out.append(ch)
        elif code < 32 or code == 127 or 0x80 <= code <= 0x9F:
            continue
        else:
            out.append(ch)
    return ''.join(out)


def truncate_to_graphemes(
    text: str, max_graphemes: int = BLUESKY_MAX_GRAPHEMES
) -> str:
    """Truncate to max graphemes with word-boundary preference + ellipsis."""
    clusters = split_graphemes(text)
    if len(clusters) <= max_graphemes:
        return text
    budget = max(1, max_graphemes - 1)  # room for '…'
    cut = ''.join(clusters[:budget]).rstrip()
    space = cut.rfind(' ')
    if space >= int(budget * 0.6):
        cut = cut[:space].rstrip()
    return cut + '…'


def validate_outbound_text(
    text: Optional[str],
    *,
    max_graphemes: int = BLUESKY_MAX_GRAPHEMES,
    truncate: bool = True,
) -> str:
    """Sanitize and validate outbound Bluesky text at the publish boundary.

    Rules:
    - Strip control chars (keep ``\\n`` / ``\\t``)
    - Reject empty / whitespace-only after sanitize
    - Truncate to ``max_graphemes`` when ``truncate=True``; else reject if over limit
    """
    if text is None:
        raise OutboundContentError('empty outbound text')

    cleaned = sanitize_outbound_text(text).strip()
    if not cleaned:
        raise OutboundContentError('empty outbound text after sanitize')

    grapheme_count = len(split_graphemes(cleaned))
    if grapheme_count > max_graphemes:
        if not truncate:
            raise OutboundContentError(
                f'outbound text exceeds {max_graphemes} graphemes '
                f'({grapheme_count})'
            )
        cleaned = truncate_to_graphemes(cleaned, max_graphemes)
        if not cleaned.strip():
            raise OutboundContentError('empty outbound text after truncate')

    return cleaned


class ContentService:
    def __init__(self, ports: ContentPorts):
        self._ports = ports

    def build_structured_prompt(self, prompt: str) -> str:
        ab_suffix = self._ports.prompt.ab_suffix or ''
        if ab_suffix:
            prompt = prompt.rstrip() + ab_suffix

        # Universal quality constraints for structured social posts.
        # Keeps prompts "human-like" and aligned with quality gate expectations.
        prompt = prompt.rstrip() + (
            "\n\nSTRICT OUTPUT CONTRACT:\n"
            "Return ONLY valid JSON object with exactly two keys: "
            "\"post_text\" and \"hashtags\".\n"
            "Do not use markdown, code fences, prefaces, or explanations.\n"
            "\"post_text\": MUST be written in English only. Natural human voice, specific "
            "and concrete, 170-240 characters, first-person perspective when appropriate, "
            "include at least one tangible detail (number, named tool, event, or example), "
            "and include one engagement hook (question, contrast, or prediction).\n"
            "\"hashtags\": 2-4 English hashtags, each starts with #, no punctuation-only tags.\n"
            "Avoid generic filler like 'this changes everything' without evidence."
        )

        if self._ports.prompt.quality_gate_regen_mode:
            prompt = prompt + (
                '\n\nIMPORTANT: The previous attempt was rejected for being too generic or repetitive. '
                'Make this post highly specific: include at least one concrete number, fact, or named example. '
                'Avoid clichés. Be original and distinct. '
                'Ensure the post has at least two engagement signals (e.g., question + strong opinion, '
                'or prediction + concrete example).'
            )
        return prompt

    def schedule_post_performance_checks(self, uri: str) -> None:
        sched = self._ports.scheduler
        for delay in (3600, 21600, 86400):
            sched.spawn(sched.delayed_performance_check(uri, delay))

    def prepare_outbound_text(
        self,
        text: Optional[str],
        *,
        max_graphemes: int = BLUESKY_MAX_GRAPHEMES,
        truncate: bool = True,
    ) -> str:
        """Validate outbound text for publish/comment paths."""
        return validate_outbound_text(
            text, max_graphemes=max_graphemes, truncate=truncate
        )
