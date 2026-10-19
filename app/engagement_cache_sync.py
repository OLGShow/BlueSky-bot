#!/usr/bin/env python3
"""Engagement cache ↔ BotMemory sync — Phase 7 / CACHE-001.

Consolidates cycle + shutdown field copies into one helper.

Import rules:
- Must not import ``bluesky_bot_v2``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, MutableMapping, Optional, Sequence, Set


def sync_engagement_caches_to_memory(
    memory: Any,
    *,
    commented_posts: Optional[Set[str]] = None,
    recent_comments: Optional[Sequence[Any]] = None,
    liked_posts: Optional[Set[str]] = None,
    reposted_posts: Optional[Set[str]] = None,
    followed_users: Optional[Set[str]] = None,
    recent_comments_keep: int = 20,
    now: Optional[datetime] = None,
    skip_missing: bool = False,
) -> None:
    """Copy in-session engagement caches onto ``memory.*_cache`` fields.

    When ``skip_missing`` is True, omit fields whose source is ``None``
    (shutdown path with hasattr guards). When False (cycle path), assign
    all provided collections (callers pass live sets/lists).
    """
    if not skip_missing:
        memory.commented_posts_cache = commented_posts
        memory.recent_comments_cache = list(recent_comments or [])[-recent_comments_keep:]
        memory.liked_posts_cache = liked_posts
        memory.reposted_posts_cache = reposted_posts
        memory.followed_users_cache = followed_users
    else:
        if commented_posts is not None:
            memory.commented_posts_cache = commented_posts
        if recent_comments is not None:
            memory.recent_comments_cache = list(recent_comments)[-recent_comments_keep:]
        if liked_posts is not None:
            memory.liked_posts_cache = liked_posts
        if reposted_posts is not None:
            memory.reposted_posts_cache = reposted_posts
        if followed_users is not None:
            memory.followed_users_cache = followed_users

    memory.last_update = now or datetime.now()


def hydrate_engagement_caches_from_memory(
    memory: Any,
) -> Mapping[str, Any]:
    """Return cache snapshots from memory for bot init (read-only view)."""
    return {
        "commented_posts": set(getattr(memory, "commented_posts_cache", set()) or set()),
        "recent_comments": list(getattr(memory, "recent_comments_cache", []) or []),
        "liked_posts": set(getattr(memory, "liked_posts_cache", set()) or set()),
        "reposted_posts": set(getattr(memory, "reposted_posts_cache", set()) or set()),
        "followed_users": set(getattr(memory, "followed_users_cache", set()) or set()),
    }
