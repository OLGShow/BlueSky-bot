#!/usr/bin/env python3
"""Content ports (Protocols) for DIP — ADR-001 Phase 2 / CONT-002.

Application services depend on these contracts only. The bot remains the
composition root and wires concrete adapters in CONT-003.

Protocol ↔ bot attribute mapping (today → ports):

| Protocol / view              | Bot source today                          |
|------------------------------|-------------------------------------------|
| PromptContextPort            | ``_current_ab_suffix``,                   |
|                              | ``_quality_gate_regen_mode``              |
| BackgroundSchedulerPort      | ``_spawn_background``,                    |
|                              | ``delayed_performance_check``             |

Import rules (ADR invariants):
- This module must not import ``bluesky_bot_v2`` or application services.
- Stdlib / typing only — keeps the ports → bot edge acyclic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable


# --- Prompt context (A/B suffix + quality-gate regen flag) ---


@runtime_checkable
class PromptContextPort(Protocol):
    """Narrow prompt flags used by ``ContentService.build_structured_prompt``."""

    @property
    def ab_suffix(self) -> str: ...

    @property
    def quality_gate_regen_mode(self) -> bool: ...


@dataclass(frozen=True)
class PromptContextView:
    """Static snapshot of prompt context (fakes / one-shot wiring)."""

    ab_suffix: str = ""
    quality_gate_regen_mode: bool = False


@dataclass
class LivePromptContext:
    """Re-resolves prompt flags on each access.

    Needed because the composition root mutates ``_current_ab_suffix`` and
    ``_quality_gate_regen_mode`` during a session; a frozen view would stale.
    """

    _get_ab_suffix: Callable[[], str]
    _get_quality_gate_regen_mode: Callable[[], bool]

    @property
    def ab_suffix(self) -> str:
        return self._get_ab_suffix()

    @property
    def quality_gate_regen_mode(self) -> bool:
        return self._get_quality_gate_regen_mode()


# --- Background scheduling (post-performance checks) ---


@runtime_checkable
class BackgroundSchedulerPort(Protocol):
    """Fire-and-forget scheduling for delayed post-performance checks."""

    def spawn(self, coro: Awaitable[Any]) -> None: ...

    def delayed_performance_check(
        self, uri: str, delay: int
    ) -> Awaitable[Any]: ...


@dataclass
class LiveBackgroundScheduler:
    """Binds spawn + delayed_performance_check callables (composition root).

    Satisfies ``BackgroundSchedulerPort`` structurally for CONT-003 wiring.
    """

    _spawn: Callable[[Awaitable[Any]], None]
    _delayed_performance_check: Callable[[str, int], Awaitable[Any]]

    def spawn(self, coro: Awaitable[Any]) -> None:
        self._spawn(coro)

    def delayed_performance_check(
        self, uri: str, delay: int
    ) -> Awaitable[Any]:
        return self._delayed_performance_check(uri, delay)


# --- Composition bundle (CONT-003 injection shape) ---


@dataclass
class ContentPorts:
    """All dependencies injected into ContentService (CONT-003).

    Bot (composition root) builds one instance from its fields and injects it;
    services never see ``AutonomousBlueskyBotV2``.
    """

    prompt: PromptContextPort
    scheduler: BackgroundSchedulerPort
