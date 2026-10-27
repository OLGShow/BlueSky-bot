#!/usr/bin/env python3
"""UTC/local traffic windows for post / engagement / follow (IMPROVEMENT_PLAN Wave 2).

No bluesky_bot_v2 import. Empty constraints → allow (backward compatible).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence, Union

Kind = str  # "post" | "engagement" | "follow"


def _zoneinfo(tz_name: str):
    try:
        import zoneinfo

        return zoneinfo.ZoneInfo(tz_name)
    except Exception:
        return timezone.utc


def current_hour(sched: Mapping[str, Any], *, now: Optional[datetime] = None) -> int:
    tz_name = str(sched.get("timezone") or "UTC")
    tz = _zoneinfo(tz_name)
    clock = now or datetime.now(tz)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=tz)
    else:
        clock = clock.astimezone(tz)
    return int(clock.hour)


def _in_quiet(hour: int, quiet_hours: Sequence[Any]) -> bool:
    try:
        return hour in {int(h) for h in quiet_hours}
    except (TypeError, ValueError):
        return False


def _in_active_windows(hour: int, windows: Sequence[Any]) -> bool:
    """Return True if hour is inside any [start, end) window (end exclusive).

    Supports wrap-around when start > end (e.g. 22→6).
    Empty windows list means «no active-window constraint».
    """
    if not windows:
        return True
    for window in windows:
        if not isinstance(window, (list, tuple)) or len(window) < 2:
            continue
        try:
            start, end = int(window[0]), int(window[1])
        except (TypeError, ValueError):
            continue
        if start <= end:
            if start <= hour < end:
                return True
        else:
            if hour >= start or hour < end:
                return True
    return False


def _kind_keys(kind: Kind) -> tuple[str, str]:
    if kind == "engagement":
        return "engagement_quiet_hours", "engagement_active_windows"
    if kind == "follow":
        return "follow_quiet_hours", "follow_active_windows"
    return "quiet_hours", "active_windows"


def is_allowed(
    sched: Optional[Mapping[str, Any]],
    kind: Kind = "post",
    *,
    now: Optional[datetime] = None,
) -> bool:
    """Whether traffic of ``kind`` is allowed under ``scheduling`` config.

    Resolution order for engagement/follow:
    1. kind-specific quiet/active keys if present (even if empty list for quiet)
    2. fall back to post ``quiet_hours`` / ``active_windows``
    3. if nothing configured → allow
    """
    cfg: Mapping[str, Any] = sched or {}
    quiet_key, active_key = _kind_keys(kind)

    has_kind_quiet = quiet_key in cfg
    has_kind_active = active_key in cfg
    quiet_hours = list(cfg.get(quiet_key) or []) if has_kind_quiet else list(
        cfg.get("quiet_hours") or []
    )
    active_windows = list(cfg.get(active_key) or []) if has_kind_active else list(
        cfg.get("active_windows") or []
    )

    # If kind-specific keys absent, we already fell back to post keys above.
    if not quiet_hours and not active_windows:
        return True

    hour = current_hour(cfg, now=now)
    if quiet_hours and _in_quiet(hour, quiet_hours):
        return False
    if active_windows and not _in_active_windows(hour, active_windows):
        return False
    return True
