#!/usr/bin/env python3
"""Thin safety layer over ActivityBudget / CircuitBreaker risk signals (PLRN-022)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "min_budget_ratio": 0.05,
    "followers_shock_abs": 50,
    "max_consecutive_errors": 5,
}


@dataclass
class SafetyStatus:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    can_credit: bool = True
    can_sync_config: bool = True
    can_publish: bool = True
    can_engagement: bool = True


def _hourly_remaining_ratio(budget_summary: Mapping[str, Any] | None) -> float | None:
    """Derive hourly remaining_ratio from ActivityBudget.summary()-shaped dicts."""
    if not budget_summary:
        return None
    if "remaining_ratio" in budget_summary:
        try:
            return float(budget_summary["remaining_ratio"])
        except (TypeError, ValueError):
            return None

    rem = budget_summary.get("remaining_hourly")
    limit = budget_summary.get("hourly_limit")
    if rem is not None and limit is not None:
        try:
            lim = float(limit)
            return (float(rem) / lim) if lim > 0 else None
        except (TypeError, ValueError):
            pass

    hourly = budget_summary.get("hourly")
    if rem is not None and isinstance(hourly, str) and "/" in hourly:
        try:
            _, lim_s = hourly.split("/", 1)
            lim = float(lim_s.strip())
            return (float(rem) / lim) if lim > 0 else None
        except (TypeError, ValueError):
            return None
    return None


class SafetyGovernor:
    """Config-driven gates for publish / credit / config sync / engagement."""

    def __init__(self, params: Optional[Mapping[str, Any]] = None) -> None:
        raw = dict(_DEFAULTS)
        if params:
            raw.update(dict(params))
        self.enabled = bool(raw.get("enabled", True))
        self.min_budget_ratio = float(raw.get("min_budget_ratio", 0.05))
        self.followers_shock_abs = float(raw.get("followers_shock_abs", 50))
        self.max_consecutive_errors = int(raw.get("max_consecutive_errors", 5))

    def evaluate(
        self,
        *,
        budget_summary: dict | None,
        circuit_open: dict[str, bool] | None,
        followers_delta_1h: float | None,
        consecutive_errors: int = 0,
    ) -> SafetyStatus:
        if not self.enabled:
            return SafetyStatus(ok=True)

        can_credit = True
        can_sync = True
        can_publish = True
        can_engagement = True
        reasons: list[str] = []

        circuits = circuit_open or {}
        if circuits.get("bluesky"):
            can_publish = False
            can_credit = False
            can_sync = False
            can_engagement = False  # follows can_publish for bluesky CB
            reasons.append("bluesky_circuit_open")

        if circuits.get("ai"):
            can_publish = False
            reasons.append("ai_circuit_open")

        ratio = _hourly_remaining_ratio(budget_summary)
        if ratio is not None and ratio < self.min_budget_ratio:
            can_publish = False
            reasons.append(
                f"budget_hourly_ratio={ratio:.4f}<{self.min_budget_ratio}"
            )

        if followers_delta_1h is not None:
            try:
                delta = float(followers_delta_1h)
            except (TypeError, ValueError):
                delta = None
            if delta is not None and abs(delta) >= self.followers_shock_abs:
                can_credit = False
                can_sync = False
                reasons.append(
                    f"followers_shock abs({delta})>={self.followers_shock_abs}"
                )

        errs = int(consecutive_errors or 0)
        if errs >= self.max_consecutive_errors:
            can_publish = False
            can_credit = False
            reasons.append(
                f"consecutive_errors={errs}>={self.max_consecutive_errors}"
            )

        return SafetyStatus(
            ok=not reasons,
            reasons=reasons,
            can_credit=can_credit,
            can_sync_config=can_sync,
            can_publish=can_publish,
            can_engagement=can_engagement,
        )
