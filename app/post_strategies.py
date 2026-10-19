#!/usr/bin/env python3
"""Post strategy registry skeleton — ADR-001 Phase 1 / REF-003.

Maps config ``post_strategies`` names (e.g. ``_create_quality_news_post``)
to callables / :class:`PostStrategy` implementations without requiring a full
extraction from ``AutonomousBlueskyBotV2``.

**Current (Phase 2 / STRAT-002):**
- ``PostStrategy`` Protocol + ``CallablePostStrategy`` adapter
- ``PostStrategyRegistry`` with ``register`` / ``get`` / ``list`` / ``resolve``
- Composition root registers **all** ``post_strategies`` config keys as bound
  methods via ``build_bound_registry`` / ``register_bound_methods``
- Runtime dispatch: ``create_scheduled_post`` uses
  ``registry.weighted_entries(config)``; duplicate-fallback uses
  ``registry.resolve(name)`` (getattr only for names not in config)

**How to use later (full strategy extraction):**

1. Extract each ``_create_*`` method into a module that implements
   ``PostStrategy.create`` (or wrap with ``CallablePostStrategy``).
2. At composition-root init, ``registry.register(name, strategy)`` for every
   config key (or auto-register from a package).
3. Keep weighted choice / quality-gate loops on resolved callables;
   learning / A/B keys stay the config **name strings**.
4. Drop bound methods from the bot once all keys resolve via the registry.

Import rules (ADR invariants):
- This module must not import ``bluesky_bot_v2`` or application services.
- Stdlib / typing only — keeps the strategies → bot edge acyclic.
"""

from __future__ import annotations

import types
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Protocol,
    Tuple,
    Union,
    runtime_checkable,
)

# Async zero-arg (or kwargs-ignored) post factory — matches today's bot methods.
PostStrategyFn = Callable[..., Awaitable[Any]]


@runtime_checkable
class PostStrategy(Protocol):
    """Narrow contract for a post-creation strategy (OCP extension point)."""

    async def create(self) -> Any:
        """Produce a post object (or None on soft failure)."""
        ...


class CallablePostStrategy:
    """Adapt a plain async callable to :class:`PostStrategy`."""

    __slots__ = ("name", "_fn")

    def __init__(self, name: str, fn: PostStrategyFn) -> None:
        if not callable(fn):
            raise TypeError(f"strategy {name!r}: expected callable, got {type(fn)!r}")
        self.name = name
        self._fn = fn

    async def create(self) -> Any:
        return await self._fn()


def _as_strategy(
    name: str,
    strategy: Union[PostStrategy, PostStrategyFn],
) -> PostStrategy:
    if isinstance(strategy, CallablePostStrategy):
        return strategy
    # Bound methods / plain functions → wrap (bot private methods today).
    if isinstance(strategy, (types.MethodType, types.FunctionType)):
        return CallablePostStrategy(name, strategy)
    create = getattr(strategy, "create", None)
    if create is not None and callable(create):
        return strategy  # type: ignore[return-value]
    if callable(strategy):
        return CallablePostStrategy(name, strategy)  # type: ignore[arg-type]
    raise TypeError(
        f"strategy {name!r}: expected PostStrategy or async callable, got {type(strategy)!r}"
    )


def _to_callable(name: str, strategy: PostStrategy) -> PostStrategyFn:
    """Return an async zero-arg callable suitable for weighted choice."""
    if isinstance(strategy, CallablePostStrategy):
        return strategy._fn
    create = strategy.create

    async def _runner() -> Any:
        return await create()

    _runner.__name__ = name
    _runner.__qualname__ = name
    return _runner


class StrategyLookupError(KeyError):
    """Raised when a strategy name is not registered."""


class PostStrategyRegistry:
    """Name → strategy map for config-driven post creation (skeleton).

    Thread-safety: intended for single-threaded asyncio composition-root use.
    """

    def __init__(self) -> None:
        self._strategies: Dict[str, PostStrategy] = {}

    def register(
        self,
        name: str,
        strategy: Union[PostStrategy, PostStrategyFn],
        *,
        overwrite: bool = True,
    ) -> None:
        """Register ``strategy`` under config key ``name``."""
        if not name or not isinstance(name, str):
            raise ValueError("strategy name must be a non-empty str")
        if not overwrite and name in self._strategies:
            raise ValueError(f"strategy already registered: {name!r}")
        self._strategies[name] = _as_strategy(name, strategy)

    def get(self, name: str) -> PostStrategy:
        """Return the registered :class:`PostStrategy` or raise."""
        try:
            return self._strategies[name]
        except KeyError as exc:
            raise StrategyLookupError(name) from exc

    def resolve(self, name: str) -> PostStrategyFn:
        """Return an async callable for weighted choice / direct await."""
        return _to_callable(name, self.get(name))

    def list(self) -> List[str]:
        """Registered strategy names (sorted for stable tests)."""
        return sorted(self._strategies.keys())

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._strategies

    def __len__(self) -> int:
        return len(self._strategies)

    def weighted_entries(
        self,
        weights: Mapping[str, float],
        *,
        skip_missing: bool = True,
    ) -> List[Tuple[PostStrategyFn, float]]:
        """Build ``[(callable, weight), ...]`` from a config weight map.

        Missing names are skipped when ``skip_missing`` is True (default);
        otherwise :class:`StrategyLookupError` is raised. Used by
        ``create_scheduled_post`` for weighted strategy dispatch.
        """
        entries: List[Tuple[PostStrategyFn, float]] = []
        for name, weight in weights.items():
            if name not in self._strategies:
                if skip_missing:
                    continue
                raise StrategyLookupError(name)
            entries.append((self.resolve(name), float(weight)))
        return entries


def register_bound_methods(
    registry: PostStrategyRegistry,
    owner: Any,
    names: Iterable[str],
    *,
    overwrite: bool = True,
) -> List[str]:
    """Register ``owner``'s bound methods by name (composition-root helper).

    Returns the list of names successfully registered (skips missing attrs).
    Callers that need missing-name diagnostics should compare against ``names``
    or use :func:`build_bound_registry`.
    """
    registered: List[str] = []
    for name in names:
        fn = getattr(owner, name, None)
        if fn is None or not callable(fn):
            continue
        registry.register(name, fn, overwrite=overwrite)
        registered.append(name)
    return registered


def build_bound_registry(
    owner: Any,
    names: Iterable[str],
    *,
    overwrite: bool = True,
) -> Tuple[PostStrategyRegistry, List[str], List[str]]:
    """Create a registry and register ``owner`` callables for ``names``.

    Returns ``(registry, registered_names, missing_names)``. Missing means the
    attribute was absent or not callable — callers should log; an empty
    ``registered_names`` with non-empty ``names`` is a hard misconfiguration.

    Import-safe: ``owner`` is any object; this module must not import the bot.
    """
    name_list = [n for n in names if isinstance(n, str) and n]
    registry = PostStrategyRegistry()
    registered = register_bound_methods(
        registry, owner, name_list, overwrite=overwrite
    )
    registered_set = set(registered)
    missing = [n for n in name_list if n not in registered_set]
    return registry, registered, missing


# Default proof set — subset of bot_config ``post_strategies`` keys (tests / demos).
DEFAULT_PROOF_STRATEGY_NAMES: Tuple[str, ...] = (
    "_create_quality_news_post",
    "_create_personal_opinion_post",
)


def build_proof_registry(owner: Any) -> PostStrategyRegistry:
    """Create a registry and register the default proof strategies from ``owner``."""
    registry, _, _ = build_bound_registry(owner, DEFAULT_PROOF_STRATEGY_NAMES)
    return registry
