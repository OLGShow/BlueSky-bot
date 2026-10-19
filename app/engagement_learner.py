"""Topic-arm engagement bandit — PLRN-011.

Wraps :class:`PolicyLearner` for relevance score multipliers. Arms are
``relevance_settings.topic_groups`` keys plus ``_other``.

Import rules:
- Must not import ``bluesky_bot_v2``.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Mapping, MutableSequence, Optional

from policy_learner import (
    CATCH_UP_24H_MAX_H,
    CATCH_UP_24H_MIN_H,
    CATCH_UP_6H_MAX_H,
    CATCH_UP_6H_MIN_H,
    PolicyLearner,
)

OTHER_ARM = "_other"
MAX_ENGAGEMENT_ACTIONS = 500
DEFAULT_STATE_PATH = "learning_state_engagement.json"


def _parse_action_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    return None


def topic_arm_keys(topic_groups: Optional[Mapping[str, Any]]) -> list[str]:
    """Ordered arm keys: topic group names + ``_other``."""
    keys = [str(k) for k in (topic_groups or {}).keys()]
    if OTHER_ARM not in keys:
        keys.append(OTHER_ARM)
    return keys


def infer_topic(
    text: str,
    topic_groups: Optional[Mapping[str, Any]],
) -> str:
    """Best-matching topic group by keyword hits; fallback ``_other``.

    Matching mirrors :func:`relevance_scoring.calculate_relevance` (token
    membership for single words, substring for multi-word phrases).
    """
    groups = topic_groups or {}
    if not groups:
        return OTHER_ARM

    text_lower = (text or "").lower()
    tokens = set(re.findall(r"\b[a-zA-Z\u0400-\u04FF]{2,}\b", text_lower))

    best_name = OTHER_ARM
    best_score = 0.0
    for group_name, group_data in groups.items():
        if not isinstance(group_data, Mapping):
            continue
        kws = group_data.get("keywords", []) or []
        weight = float(group_data.get("weight", 0.05) or 0.05)
        hits = 0
        for kw in kws:
            kw_l = str(kw).lower()
            parts = kw_l.split()
            if len(parts) == 1:
                if parts[0] in tokens:
                    hits += 1
            elif kw_l in text_lower:
                hits += 1
        if hits <= 0:
            continue
        score = weight * float(hits)
        if score > best_score:
            best_score = score
            best_name = str(group_name)
    return best_name if best_score > 0 else OTHER_ARM


def arm_mean(arm: Mapping[str, Any]) -> float:
    """Beta mean α/(α+β) in [0, 1]."""
    alpha = max(1e-9, float(arm.get("alpha", 1.0)))
    beta = max(1e-9, float(arm.get("beta", 1.0)))
    return alpha / (alpha + beta)


def topic_multiplier_from_mean(mean: float) -> float:
    """Map mean∈[0,1] → multiplier∈[0.5, 1.5]."""
    m = max(0.0, min(1.0, float(mean)))
    return 0.5 + m


def append_engagement_action(
    actions: MutableSequence[dict],
    action: dict,
    *,
    max_n: int = MAX_ENGAGEMENT_ACTIONS,
) -> dict:
    """Append action dict and trim list to ``max_n`` (in-place)."""
    actions.append(action)
    if max_n > 0 and len(actions) > max_n:
        # Keep newest; mutate caller's list object when possible
        trimmed = list(actions)[-max_n:]
        try:
            actions[:] = trimmed
        except TypeError:
            pass
    return action


def eligible_engagement_catch_up_checks(
    action: dict,
    now: Optional[datetime] = None,
) -> list[str]:
    """Return check_ids due for restart catch-up on an engagement action.

    Requires ``uri`` + ``topic``. Windows match strategy catch-up:
    ``6h``∈[6h,36h), ``24h``∈[24h,48h).
    """
    if not isinstance(action, dict):
        return []
    if not action.get("uri") or not action.get("topic"):
        return []

    ref = now if now is not None else datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)

    ts = _parse_action_ts(action.get("ts"))
    if ts is None:
        ts = _parse_action_ts(action.get("timestamp"))
    if ts is None:
        return []
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    age_hours = (ref - ts).total_seconds() / 3600.0
    if age_hours < 0:
        return []

    rewarded = action.get("rewarded_checks") or []
    if not isinstance(rewarded, list):
        rewarded = []

    checks: list[str] = []
    if (
        CATCH_UP_6H_MIN_H <= age_hours < CATCH_UP_6H_MAX_H
        and "6h" not in rewarded
    ):
        checks.append("6h")
    if (
        CATCH_UP_24H_MIN_H <= age_hours < CATCH_UP_24H_MAX_H
        and "24h" not in rewarded
    ):
        checks.append("24h")
    return checks


def build_like_action(
    *,
    topic: str,
    uri: str,
    ts: Optional[str] = None,
    kind: str = "like",
) -> dict[str, Any]:
    """New engagement action ledger entry."""
    return {
        "kind": kind,
        "topic": topic or OTHER_ARM,
        "uri": uri,
        "ts": ts or datetime.now(timezone.utc).isoformat(),
        "rewarded_checks": [],
    }


class EngagementLearner:
    """Facade: topic multipliers + credit via underlying PolicyLearner."""

    def __init__(
        self,
        learner: PolicyLearner,
        topic_groups: Optional[Mapping[str, Any]] = None,
        *,
        enabled: bool = True,
    ):
        self.learner = learner
        self.topic_groups: dict[str, Any] = dict(topic_groups or {})
        self.enabled = bool(enabled)

    @classmethod
    def load(
        cls,
        config: Mapping[str, Any],
        *,
        base_params: Optional[Mapping[str, Any]] = None,
    ) -> "EngagementLearner":
        """Load from ``engagement_learning`` + ``relevance_settings`` in config."""
        eng = dict(config.get("engagement_learning") or {})
        rel = config.get("relevance_settings") or {}
        topic_groups = dict(rel.get("topic_groups") or {})
        arms = topic_arm_keys(topic_groups)

        params: dict[str, Any] = dict(base_params or {})
        # Domain overrides (share/ε); ignore non-PolicyLearner knobs
        for key in ("max_arm_share_24h", "epsilon", "reward_scale"):
            if key in eng and eng[key] is not None:
                params[key] = eng[key]
        state_path = eng.get("state_path") or DEFAULT_STATE_PATH
        enabled = bool(eng.get("enabled", True))

        even = 1.0 / len(arms) if arms else 1.0
        bootstrap = {k: even for k in arms}
        learner = PolicyLearner.load(
            path=str(state_path),
            params=params,
            arm_keys=arms,
            bootstrap_weights=bootstrap,
        )
        learner.sync_arms_with_config(arms, bootstrap)
        return cls(learner, topic_groups, enabled=enabled)

    def infer_topic(self, text: str) -> str:
        return infer_topic(text, self.topic_groups)

    def topic_multiplier(self, topic: str) -> float:
        """Return score multiplier in [0.5, 1.5]; 1.0 when disabled."""
        if not self.enabled:
            return 1.0
        key = topic if topic in self.learner.arms else OTHER_ARM
        arm = self.learner.arms.get(key)
        if arm is None:
            return 1.0
        return topic_multiplier_from_mean(arm_mean(arm))

    def credit(
        self,
        topic: str,
        likes,
        replies,
        reposts,
        check_id: str,
    ) -> bool:
        """Credit topic arm (PolicyLearner arg order: likes, reposts, replies)."""
        if not self.enabled:
            return False
        key = topic if topic in self.learner.arms else OTHER_ARM
        return self.learner.credit(key, likes, reposts, replies, check_id)

    def record_action(
        self,
        actions: MutableSequence[dict],
        *,
        kind: str,
        topic: str,
        uri: str,
        ts: Optional[str] = None,
    ) -> dict:
        """Build action, append to bot-owned list, trim to 500."""
        action = build_like_action(kind=kind, topic=topic, uri=uri, ts=ts)
        append_engagement_action(actions, action)
        return action

    def sync_arms(self) -> None:
        arms = topic_arm_keys(self.topic_groups)
        even = 1.0 / len(arms) if arms else 1.0
        self.learner.sync_arms_with_config(arms, {k: even for k in arms})

    def save(self) -> None:
        self.learner.save()

    def maybe_decay(self) -> None:
        self.learner.maybe_decay()

    def report(self) -> dict:
        return self.learner.report()

    def action_credit_delays_hours(self, config: Mapping[str, Any]) -> list[float]:
        eng = config.get("engagement_learning") or {}
        raw = eng.get("action_credit_delays_hours", [6, 24])
        if not isinstance(raw, (list, tuple)) or not raw:
            return [6.0, 24.0]
        out: list[float] = []
        for h in raw:
            try:
                out.append(float(h))
            except (TypeError, ValueError):
                continue
        return out or [6.0, 24.0]
