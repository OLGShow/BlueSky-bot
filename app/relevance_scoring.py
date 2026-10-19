#!/usr/bin/env python3
"""Post relevance scoring — thin-shell REL-001.

Extracts former ``AutonomousBlueskyBotV2.calculate_relevance``.

Import rules:
- Must not import ``bluesky_bot_v2``.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Mapping, MutableMapping, Optional

logger = logging.getLogger(__name__)


def calculate_relevance(
    text: str,
    post: Any,
    relevance_settings: Optional[Mapping[str, Any]] = None,
) -> float:
    """Component score: topical + structure + engagement (0..1).

    ``text`` is expected already lowercased by callers that pass
    ``text.lower()`` (parity with former bot method).
    """
    rel: Mapping[str, Any] = relevance_settings or {}
    topic_groups = rel.get("topic_groups", {}) or {}
    topical_max = rel.get("topical_max", 0.45)
    kw_per_match = rel.get("keyword_per_match", 0.05)
    hashtag_bonus_val = rel.get("hashtag_bonus", 0.08)
    question_bonus_val = rel.get("question_bonus", 0.07)
    length_range = rel.get("optimal_length_range", [80, 300])
    length_bonus_val = rel.get("length_bonus", 0.05)
    eng_log_base = rel.get("engagement_log_base", 10)
    eng_max = rel.get("engagement_max", 0.25)

    text_lower = text.lower()
    tokens = set(re.findall(r"\b[a-zA-Z\u0400-\u04FF]{2,}\b", text_lower))

    topical = 0.0
    matched_groups: MutableMapping[str, list] = {}
    for group_name, group_data in topic_groups.items():
        kws = group_data.get("keywords", [])
        weight = group_data.get("weight", kw_per_match)
        hits = []
        for kw in kws:
            kw_parts = kw.lower().split()
            if len(kw_parts) == 1:
                if kw_parts[0] in tokens:
                    hits.append(kw)
            else:
                if kw.lower() in text_lower:
                    hits.append(kw)
        if hits:
            matched_groups[group_name] = hits
            topical += weight * len(hits)
    topical = min(topical, topical_max)

    structure = 0.0
    hashtag_count = text.count("#")
    if hashtag_count > 0:
        structure += hashtag_bonus_val
    if "?" in text:
        structure += question_bonus_val
    text_len = len(text)
    if len(length_range) >= 2 and length_range[0] <= text_len <= length_range[1]:
        structure += length_bonus_val

    likes = getattr(post.post, "like_count", 0) or 0
    reposts_count = getattr(post.post, "repost_count", 0) or 0
    raw_engagement = likes + reposts_count * 2
    if raw_engagement > 0 and eng_log_base > 1:
        eng_score = (
            min(
                math.log(1 + raw_engagement, eng_log_base)
                / math.log(1000, eng_log_base),
                1.0,
            )
            * eng_max
        )
    else:
        eng_score = 0.0

    final = min(topical + structure + eng_score, 1.0)

    groups_str = (
        ", ".join(f"{g}({len(h)})" for g, h in matched_groups.items())
        if matched_groups
        else "-"
    )
    logger.info(
        "      📊 score=%.2f  topical=%.2f[%s]  struct=%.2f  engage=%.2f(%sL+%sR=%s)",
        final,
        topical,
        groups_str,
        structure,
        eng_score,
        likes,
        reposts_count,
        raw_engagement,
    )

    return final
