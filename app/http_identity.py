#!/usr/bin/env python3
"""
HTTP identity helpers — User-Agent pool (Wave 3.1) + proxy stub (Wave 3.2).

UA is sticky per process day (``rotate=daily``) or for the process lifetime
(``rotate=never|process``). Proxy helpers read ``PROXY_URLS`` from the
environment but are **not** wired into ATProto; callers may pass the URL to
aiohttp only when ``proxy.enabled`` is true.
"""

from __future__ import annotations

import hashlib
import os
import random
from datetime import datetime, timezone
from typing import Any, Mapping, MutableMapping, Optional, Sequence

DEFAULT_USER_AGENTS: tuple[str, ...] = (
    "BlueSky-Bot/2.1 (analytics)",
    "BlueSky-Bot/2.1 (engagement)",
)

_VALID_ROTATE = frozenset({"daily", "never", "process"})

# Process-local sticky state (tests may call reset_identity_state).
_ua_state: dict[str, Any] = {
    "ua": None,
    "day_key": None,
    "rotate": None,
    "pool_key": None,
}
_proxy_state: dict[str, Any] = {
    "url": None,
    "bucket": None,
    "pool_key": None,
}


def reset_identity_state() -> None:
    """Clear sticky UA / proxy selection (hermetic tests)."""
    _ua_state.update(ua=None, day_key=None, rotate=None, pool_key=None)
    _proxy_state.update(url=None, bucket=None, pool_key=None)


def _as_mapping(config: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    return config if isinstance(config, Mapping) else {}


def _user_agent_pool(config: Optional[Mapping[str, Any]]) -> list[str]:
    identity = _as_mapping(config).get("http_identity") or {}
    raw = identity.get("user_agents") if isinstance(identity, Mapping) else None
    agents: list[str] = []
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        for item in raw:
            text = str(item).strip()
            if text:
                agents.append(text)
    return agents or list(DEFAULT_USER_AGENTS)


def _rotate_mode(config: Optional[Mapping[str, Any]]) -> str:
    identity = _as_mapping(config).get("http_identity") or {}
    mode = str((identity or {}).get("rotate") or "daily").strip().lower()
    return mode if mode in _VALID_ROTATE else "daily"


def _day_key(now: Optional[datetime] = None) -> str:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _pool_fingerprint(pool: Sequence[str]) -> str:
    return "\0".join(pool)


def _stable_index(seed: str, size: int) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % size


def get_user_agent(
    config: Optional[Mapping[str, Any]] = None,
    *,
    now: Optional[datetime] = None,
) -> str:
    """Return a sticky User-Agent from config pool (or Bluesky-Bot defaults)."""
    pool = _user_agent_pool(config)
    rotate = _rotate_mode(config)
    pool_key = _pool_fingerprint(pool)
    day = _day_key(now)

    sticky = _ua_state["ua"]
    same_pool = _ua_state["pool_key"] == pool_key
    same_rotate = _ua_state["rotate"] == rotate

    if sticky and same_pool and same_rotate:
        if rotate == "daily" and _ua_state["day_key"] != day:
            pass  # day rolled — re-pick below
        else:
            return str(sticky)

    if rotate == "daily":
        index = _stable_index(f"ua:{day}:{pool_key}", len(pool))
        chosen = pool[index]
        _ua_state["day_key"] = day
    else:
        # never | process — one pick for the process lifetime
        chosen = random.choice(pool)
        _ua_state["day_key"] = None

    _ua_state["ua"] = chosen
    _ua_state["rotate"] = rotate
    _ua_state["pool_key"] = pool_key
    return chosen


def proxy_enabled(config: Optional[Mapping[str, Any]] = None) -> bool:
    """Feature flag; default False (Wave 3.2 stub — off in live)."""
    proxy = _as_mapping(config).get("proxy") or {}
    if not isinstance(proxy, Mapping):
        return False
    return bool(proxy.get("enabled", False))


def _proxy_urls(env: Mapping[str, str]) -> list[str]:
    raw = str(env.get("PROXY_URLS") or "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _proxy_bucket(sticky_hours: int, now: Optional[datetime] = None) -> str:
    """Bucket key for sticky proxy rotation (process lifetime if hours <= 0)."""
    if sticky_hours <= 0:
        return "process"
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    epoch_h = int(moment.timestamp() // 3600)
    return f"h{epoch_h // sticky_hours}"


def resolve_proxy_url(
    config: Optional[Mapping[str, Any]] = None,
    env: Optional[Mapping[str, str]] = None,
    *,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """Sticky proxy URL for aiohttp when enabled; never inject into ATProto.

    Reads comma-separated ``PROXY_URLS`` from ``env`` (defaults to ``os.environ``).
    Returns ``None`` when disabled or no URLs are configured.
    """
    if not proxy_enabled(config):
        return None

    environ: Mapping[str, str]
    if env is None:
        environ = os.environ
    else:
        environ = env

    urls = _proxy_urls(environ)
    if not urls:
        return None

    proxy_cfg = _as_mapping(config).get("proxy") or {}
    try:
        sticky_hours = int(proxy_cfg.get("sticky_hours", 24)) if isinstance(proxy_cfg, Mapping) else 24
    except (TypeError, ValueError):
        sticky_hours = 24

    pool_key = _pool_fingerprint(urls)
    bucket = _proxy_bucket(sticky_hours, now=now)

    if (
        _proxy_state["url"]
        and _proxy_state["pool_key"] == pool_key
        and _proxy_state["bucket"] == bucket
    ):
        return str(_proxy_state["url"])

    index = _stable_index(f"proxy:{bucket}:{pool_key}", len(urls))
    chosen = urls[index]
    _proxy_state["url"] = chosen
    _proxy_state["bucket"] = bucket
    _proxy_state["pool_key"] = pool_key
    return chosen


def aiohttp_proxy_kwargs(
    config: Optional[Mapping[str, Any]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> MutableMapping[str, str]:
    """Optional ``proxy=`` kwargs for aiohttp request/session helpers.

    Empty when proxy is disabled — safe default for live traffic.
    """
    url = resolve_proxy_url(config, env)
    if not url:
        return {}
    return {"proxy": url}
