#!/usr/bin/env python3
"""One-tick bot cycle orchestration — Phase 7 / CYCLE-001.

Extracts the *body* of one successful loop iteration from
``AutonomousBlueskyBotV2.run_bot_cycle`` behind narrow ports.

The bot keeps ``while True``, authenticate, sleep/backoff, and ownership of
mutable counters (``cycle_count``, ``last_post_time``).

Import rules:
- Must not import ``bluesky_bot_v2``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Mapping, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class BotCyclePorts(Protocol):
    """Narrow adapters for one tick (implementations live on the bot)."""

    def update_heartbeat(self) -> None: ...

    def reset_consecutive_errors(self) -> None: ...

    def engagement_mode(self) -> str: ...

    async def smart_engagement(self) -> None: ...

    async def follow_strategy(self) -> None: ...

    def follow_every_n_cycles(self) -> int: ...

    def post_interval_minutes(self) -> float: ...

    def is_posting_window(self) -> bool: ...

    def is_engagement_window(self) -> bool: ...

    def is_follow_window(self) -> bool: ...

    async def create_scheduled_post(self) -> None: ...

    async def update_posts_with_real_metrics(self) -> None: ...

    def learn_from_memory(self) -> None: ...

    def trim_in_memory_caches(self) -> None: ...

    def sync_duplicate_caches_to_memory(self) -> None: ...

    def save_memory(self) -> None: ...

    def session_stats(self) -> Mapping[str, Any]: ...

    def daily_post_counts(self) -> tuple[int, int]: ...

    def cleanup_old_content_hashes(self) -> None: ...

    def cleanup_old_commented_posts(self) -> None: ...

    def compact_action_ledger(self) -> None: ...

    def cleanup_log_budget(self) -> tuple[int, int]: ...

    def rotate_rss(self) -> None: ...

    def generate_and_save_daily_report(self) -> None: ...

    async def analyze_post_diversity(self) -> None: ...

    async def health_monitor(self) -> Mapping[str, Any]: ...

    async def emergency_recovery(self) -> bool: ...

    def persist_session(self) -> None: ...

    async def maybe_refresh_follower_cohort(self, cycle_count: int = 0) -> None: ...


@dataclass
class CallableBotCyclePorts:
    """Composition-root bundle of callables implementing :class:`BotCyclePorts`."""

    _update_heartbeat: Callable[[], None]
    _reset_consecutive_errors: Callable[[], None]
    _engagement_mode: Callable[[], str]
    _smart_engagement: Callable[[], Awaitable[None]]
    _follow_strategy: Callable[[], Awaitable[None]]
    _follow_every_n_cycles: Callable[[], int]
    _post_interval_minutes: Callable[[], float]
    _is_posting_window: Callable[[], bool]
    _is_engagement_window: Callable[[], bool]
    _is_follow_window: Callable[[], bool]
    _create_scheduled_post: Callable[[], Awaitable[None]]
    _update_posts_with_real_metrics: Callable[[], Awaitable[None]]
    _learn_from_memory: Callable[[], None]
    _trim_in_memory_caches: Callable[[], None]
    _sync_duplicate_caches_to_memory: Callable[[], None]
    _save_memory: Callable[[], None]
    _session_stats: Callable[[], Mapping[str, Any]]
    _daily_post_counts: Callable[[], tuple[int, int]]
    _cleanup_old_content_hashes: Callable[[], None]
    _cleanup_old_commented_posts: Callable[[], None]
    _compact_action_ledger: Callable[[], None]
    _cleanup_log_budget: Callable[[], tuple[int, int]]
    _rotate_rss: Callable[[], None]
    _generate_and_save_daily_report: Callable[[], None]
    _analyze_post_diversity: Callable[[], Awaitable[None]]
    _health_monitor: Callable[[], Awaitable[Mapping[str, Any]]]
    _emergency_recovery: Callable[[], Awaitable[bool]]
    _persist_session: Callable[[], None]
    # W1-006: optional; default no-op so hermetic cycle tests stay unchanged.
    _maybe_refresh_follower_cohort: Optional[Callable[[int], Awaitable[None]]] = None

    def update_heartbeat(self) -> None:
        self._update_heartbeat()

    def reset_consecutive_errors(self) -> None:
        self._reset_consecutive_errors()

    def engagement_mode(self) -> str:
        return self._engagement_mode()

    async def smart_engagement(self) -> None:
        await self._smart_engagement()

    async def follow_strategy(self) -> None:
        await self._follow_strategy()

    def follow_every_n_cycles(self) -> int:
        try:
            return max(1, int(self._follow_every_n_cycles()))
        except Exception:
            return 2

    def post_interval_minutes(self) -> float:
        return self._post_interval_minutes()

    def is_posting_window(self) -> bool:
        return self._is_posting_window()

    def is_engagement_window(self) -> bool:
        try:
            return bool(self._is_engagement_window())
        except Exception:
            return True

    def is_follow_window(self) -> bool:
        try:
            return bool(self._is_follow_window())
        except Exception:
            return True

    async def create_scheduled_post(self) -> None:
        await self._create_scheduled_post()

    async def update_posts_with_real_metrics(self) -> None:
        await self._update_posts_with_real_metrics()

    def learn_from_memory(self) -> None:
        self._learn_from_memory()

    def trim_in_memory_caches(self) -> None:
        self._trim_in_memory_caches()

    def sync_duplicate_caches_to_memory(self) -> None:
        self._sync_duplicate_caches_to_memory()

    def save_memory(self) -> None:
        self._save_memory()

    def session_stats(self) -> Mapping[str, Any]:
        return self._session_stats()

    def daily_post_counts(self) -> tuple[int, int]:
        return self._daily_post_counts()

    def cleanup_old_content_hashes(self) -> None:
        self._cleanup_old_content_hashes()

    def cleanup_old_commented_posts(self) -> None:
        self._cleanup_old_commented_posts()

    def compact_action_ledger(self) -> None:
        self._compact_action_ledger()

    def cleanup_log_budget(self) -> tuple[int, int]:
        return self._cleanup_log_budget()

    def rotate_rss(self) -> None:
        self._rotate_rss()

    def generate_and_save_daily_report(self) -> None:
        self._generate_and_save_daily_report()

    async def analyze_post_diversity(self) -> None:
        await self._analyze_post_diversity()

    async def health_monitor(self) -> Mapping[str, Any]:
        return await self._health_monitor()

    async def emergency_recovery(self) -> bool:
        return await self._emergency_recovery()

    def persist_session(self) -> None:
        self._persist_session()

    async def maybe_refresh_follower_cohort(self, cycle_count: int = 0) -> None:
        hook = self._maybe_refresh_follower_cohort
        if hook is None:
            return
        await hook(cycle_count)


@dataclass
class TickResult:
    """Outcome of one cycle tick."""

    last_post_time: datetime
    stop: bool = False


class BotCycleRunner:
    """Orchestrates one successful cycle tick (no sleep / no auth)."""

    __slots__ = ("_ports",)

    def __init__(self, ports: BotCyclePorts) -> None:
        self._ports = ports

    async def tick(
        self,
        cycle_count: int,
        last_post_time: datetime,
        *,
        now: Optional[Callable[[], datetime]] = None,
    ) -> TickResult:
        """Run one tick; return updated ``last_post_time`` and optional stop."""
        clock = now or datetime.now
        ports = self._ports

        ports.update_heartbeat()
        ports.reset_consecutive_errors()
        logger.info("🔄 Цикл %s - %s", cycle_count + 1, clock())

        engagement_mode = ports.engagement_mode()
        run_engagement = engagement_mode != "mention_only"

        if run_engagement:
            eng_ok = True
            try:
                eng_ok = bool(ports.is_engagement_window())
            except Exception:
                eng_ok = True
            if eng_ok:
                await ports.smart_engagement()
            else:
                logger.info("🌙 Quiet hours — smart engagement пропущен")

            every_n = ports.follow_every_n_cycles()
            if cycle_count % every_n == 0:
                follow_ok = True
                try:
                    follow_ok = bool(ports.is_follow_window())
                except Exception:
                    follow_ok = True
                if follow_ok:
                    await ports.follow_strategy()
                else:
                    logger.info("🌙 Quiet hours — follow strategy пропущена")
        else:
            logger.info("🔇 Engagement пропущен (mode=mention_only)")

        time_since_last_post = clock() - last_post_time
        min_interval = timedelta(minutes=ports.post_interval_minutes())
        in_posting_window = ports.is_posting_window()

        updated_last_post = last_post_time
        if time_since_last_post >= min_interval and in_posting_window:
            await ports.create_scheduled_post()
            updated_last_post = clock()
        elif not in_posting_window:
            logger.info("🌙 Quiet hours / вне active window — постинг отложен")
        else:
            remaining = min_interval - time_since_last_post
            logger.info("⏳ До следующего поста осталось: %s", remaining)

        if cycle_count % 10 == 0:
            await ports.update_posts_with_real_metrics()
            ports.learn_from_memory()

        if cycle_count % 20 == 0:
            ports.trim_in_memory_caches()
            ports.sync_duplicate_caches_to_memory()
            ports.save_memory()
            daily_count, daily_max = ports.daily_post_counts()
            logger.info("💾 Память сохранена (включая кэши защиты от дубликатов)")
            logger.info("📊 Статистика сессии: %s", ports.session_stats())
            logger.info("📊 Постов за день: %s/%s", daily_count, daily_max)

        if cycle_count % 144 == 0 and cycle_count > 0:
            ports.cleanup_old_content_hashes()
            ports.cleanup_old_commented_posts()
            ports.compact_action_ledger()
            removed_files, removed_bytes = ports.cleanup_log_budget()
            if removed_files:
                logger.warning(
                    "🧹 Очистка логов по бюджету: удалено %s файлов, "
                    "освобождено %.1f MB",
                    removed_files,
                    removed_bytes / (1024 * 1024),
                )

        if cycle_count % 50 == 0 and cycle_count > 0:
            logger.info("🔧 RSS rotation...")
            ports.rotate_rss()

        if cycle_count % 144 == 0 and cycle_count > 0:
            ports.generate_and_save_daily_report()

        if cycle_count % 30 == 0 and cycle_count > 0:
            logger.info("📊 Запуск анализа разнообразия постов...")
            await ports.analyze_post_diversity()

        if cycle_count % 20 == 0 and cycle_count > 0:
            health_status = await ports.health_monitor()
            if health_status.get("overall_health") == "critical":
                logger.warning(
                    "🚨 Критическое состояние здоровья! "
                    "Запуск экстренного восстановления..."
                )
                recovery_success = await ports.emergency_recovery()
                if not recovery_success:
                    logger.error("❌ Экстренное восстановление не удалось")
                    return TickResult(last_post_time=updated_last_post, stop=True)

        if cycle_count % 10 == 0 and cycle_count > 0:
            ports.persist_session()

        # W1-006: rare follower cohort snapshot (no-op unless wired).
        # Use getattr so RecordingPorts / older fakes stay hermetic.
        cohort_hook = getattr(ports, "maybe_refresh_follower_cohort", None)
        if cohort_hook is not None:
            await cohort_hook(cycle_count)

        return TickResult(last_post_time=updated_last_post, stop=False)
