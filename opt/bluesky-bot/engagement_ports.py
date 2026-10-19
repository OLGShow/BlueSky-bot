#!/usr/bin/env python3
"""Engagement ports (Protocols) for DIP — ADR-001 Phase 1 / REF-001.

Application services depend on these contracts only. The bot remains the
composition root and wires concrete adapters in REF-002.

Protocol ↔ bot attribute mapping (today → ports):

| Protocol / view              | Bot source today                          |
|------------------------------|-------------------------------------------|
| EngagementClientPort         | ``bot.bluesky_client``                    |
| ActionLedgerPort             | ``bot.action_ledger``                     |
| ActivityBudgetPort           | ``bot.activity_budget``                   |
| DryRunPort / DryRunGate      | ``bot.dry_run`` + ``bot.dry_run_log``     |
| EngagementStatsPort          | ``bot.session_stats``                     |
| EngagementIdentityPort       | ``liked_posts``, ``reposted_posts``,      |
|                              | ``followed_users``, ``recent_repost_authors`` |
| EngagementConfigView         | ``bot.config`` engagement_mode / whitelist|

Import rules (ADR invariants):
- This module must not import ``bluesky_bot_v2`` or application services.
- Stdlib / typing only — keeps the ports → bot edge acyclic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    MutableMapping,
    MutableSequence,
    MutableSet,
    Optional,
    Protocol,
    runtime_checkable,
)


# --- Client (ATProto write ops used by engagement) ---


@runtime_checkable
class EngagementClientPort(Protocol):
    """Bluesky/ATProto client ops needed by EngagementService."""

    async def like(self, uri: str, cid: str) -> Any: ...

    async def repost(self, uri: str, cid: str) -> Any: ...

    async def follow(self, did: str) -> Any: ...


# --- Action ledger (idempotency) ---


@runtime_checkable
class ActionLedgerPort(Protocol):
    """Append-only action keys for like/repost/follow idempotency."""

    def contains(self, key: str) -> bool: ...

    def record(self, key: str) -> None: ...


# --- Activity budget ---


@runtime_checkable
class ActivityBudgetPort(Protocol):
    """Point budget gate for ATProto write actions."""

    def can_spend(self, action: str) -> bool: ...

    def spend(self, action: str) -> None: ...


class UnlimitedBudget:
    """No-op budget when the composition root has no ActivityBudget."""

    def can_spend(self, action: str) -> bool:
        return True

    def spend(self, action: str) -> None:
        return None


# --- Dry-run ---


@runtime_checkable
class DryRunLoggerPort(Protocol):
    """Optional sink used when dry-run is enabled (``DryRunAction`` today)."""

    def log(self, action: str, **kwargs: Any) -> None: ...


@runtime_checkable
class DryRunPort(Protocol):
    """Dry-run flag + log hook used by engagement write paths."""

    @property
    def enabled(self) -> bool: ...

    def log(self, action: str, **kwargs: Any) -> None: ...


@dataclass
class DryRunGate:
    """Thin facade over ``bot.dry_run`` + optional ``bot.dry_run_log``.

    Satisfies ``DryRunPort`` structurally for REF-002 wiring and fakes.
    """

    enabled: bool
    _logger: Optional[DryRunLoggerPort] = None

    def log(self, action: str, **kwargs: Any) -> None:
        if self.enabled and self._logger is not None:
            self._logger.log(action, **kwargs)


# --- Session stats ---


@runtime_checkable
class EngagementStatsPort(Protocol):
    """Mutable session counters (``likes_given``, ``reposts_made``, …)."""

    def __getitem__(self, key: str) -> Any: ...

    def __setitem__(self, key: str, value: Any) -> None: ...


# --- Identity / dedupe sets ---


@runtime_checkable
class EngagementIdentityPort(Protocol):
    """In-memory sets/lists that prevent duplicate engagement actions."""

    @property
    def liked_posts(self) -> MutableSet[str]: ...

    @property
    def reposted_posts(self) -> MutableSet[str]: ...

    @property
    def followed_users(self) -> MutableSet[str]: ...

    @property
    def recent_repost_authors(self) -> MutableSequence[str]: ...


@dataclass
class EngagementIdentityView:
    """Concrete identity bundle; bot fields can be passed by reference."""

    liked_posts: MutableSet[str]
    reposted_posts: MutableSet[str]
    followed_users: MutableSet[str]
    recent_repost_authors: MutableSequence[str]


@dataclass
class LiveEngagementIdentity:
    """Identity port that re-resolves collections on each access.

    Needed because the composition root may reassign ``liked_posts`` /
    ``followed_users`` (trim/cleanup) to a new set object; a static
    ``EngagementIdentityView`` would keep the stale reference.
    """

    _liked_posts: Callable[[], MutableSet[str]]
    _reposted_posts: Callable[[], MutableSet[str]]
    _followed_users: Callable[[], MutableSet[str]]
    _recent_repost_authors: Callable[[], MutableSequence[str]]

    @property
    def liked_posts(self) -> MutableSet[str]:
        return self._liked_posts()

    @property
    def reposted_posts(self) -> MutableSet[str]:
        return self._reposted_posts()

    @property
    def followed_users(self) -> MutableSet[str]:
        return self._followed_users()

    @property
    def recent_repost_authors(self) -> MutableSequence[str]:
        return self._recent_repost_authors()


# --- Engagement config (narrow view; not full bot.config) ---


@runtime_checkable
class EngagementConfigPort(Protocol):
    """Narrow engagement policy (mode + whitelist)."""

    @property
    def mode(self) -> str: ...

    @property
    def whitelist(self) -> frozenset[str]: ...


@dataclass(frozen=True)
class EngagementConfigView:
    """Narrow engagement policy view extracted from bot config."""

    mode: str = "open"
    whitelist: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_mapping(cls, config: Optional[MutableMapping[str, Any]] = None) -> EngagementConfigView:
        cfg = config or {}
        mode = str(cfg.get("engagement_mode", "open") or "open")
        raw = cfg.get("engagement_whitelist", []) or []
        return cls(mode=mode, whitelist=frozenset(str(x) for x in raw))


@dataclass
class LiveEngagementConfig:
    """Re-reads engagement policy from a live mapping on each access."""

    _get_config: Callable[[], MutableMapping[str, Any]]

    @property
    def mode(self) -> str:
        return EngagementConfigView.from_mapping(self._get_config()).mode

    @property
    def whitelist(self) -> frozenset[str]:
        return EngagementConfigView.from_mapping(self._get_config()).whitelist


# --- Composition bundle (REF-002 injection shape) ---


@dataclass
class EngagementPorts:
    """All dependencies EngagementService will take after REF-002.

    Bot (composition root) builds one instance from its fields and injects it;
    services never see ``AutonomousBlueskyBotV2``.
    """

    client: EngagementClientPort
    ledger: ActionLedgerPort
    budget: ActivityBudgetPort
    dry_run: DryRunPort
    stats: EngagementStatsPort
    identity: EngagementIdentityPort
    config: EngagementConfigPort
