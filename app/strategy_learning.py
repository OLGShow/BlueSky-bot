#!/usr/bin/env python3
"""Legacy LEARN-001 helpers (compute-only).

Runtime strategy weights are owned by ``PolicyLearner`` (PLRN-005+).
``apply_strategy_weights_from_outcomes`` was removed — do not reintroduce
dual writers. Constants / ``compute_updated_strategy_weights`` kept for
tests and offline analysis only.

Import rules:
- Must not import ``bluesky_bot_v2``.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

WEIGHT_MIN = 0.05
WEIGHT_MAX = 0.50
WEIGHT_DELTA = 0.1


def _topic_key_from_strategy_name(fname: str) -> str:
    """Fuzzy topic key derived from a ``post_strategies`` config key."""
    return (
        fname.lstrip("_create_")
        .replace("quality_", "")
        .replace("_post", "")
        .replace("_", " ")
        .strip()
    )


def _best_outcome_match(
    outcomes: Mapping[str, Any], topic_key: str
) -> Optional[str]:
    if not outcomes:
        return None
    return max(
        outcomes.keys(),
        key=lambda k: len(set(k.split()) & set(topic_key.split())),
        default=None,
    )


def _avg_er(entry: Mapping[str, Any]) -> float:
    count = max(int(entry.get("count", 0) or 0), 1)
    return float(entry.get("total_er", 0.0) or 0.0) / count


def compute_updated_strategy_weights(
    topic_outcomes: Mapping[str, Mapping[str, Any]],
    post_strategies: Mapping[str, float],
    *,
    delta: float = WEIGHT_DELTA,
    weight_min: float = WEIGHT_MIN,
    weight_max: float = WEIGHT_MAX,
) -> Tuple[Dict[str, float], bool]:
    """Return updated weights and whether any weight changed.

    Offline/helper only — not used by the live bot credit path.
    """
    if not topic_outcomes:
        return dict(post_strategies), False

    avg_all = sum(_avg_er(v) for v in topic_outcomes.values()) / len(
        topic_outcomes
    )
    updated: Dict[str, float] = dict(post_strategies)
    changed = False

    for fname, weight in list(post_strategies.items()):
        topic_key = _topic_key_from_strategy_name(str(fname))
        best_match = _best_outcome_match(topic_outcomes, topic_key)
        if not best_match:
            continue
        er_topic = _avg_er(topic_outcomes[best_match])
        direction = delta if er_topic > avg_all else -delta
        new_weight = round(
            max(weight_min, min(weight_max, float(weight) * (1 + direction))),
            3,
        )
        if new_weight != weight:
            updated[str(fname)] = new_weight
            changed = True

    return updated, changed
