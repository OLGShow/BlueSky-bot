#!/usr/bin/env python3
"""HealthService — health monitor + emergency recovery (thin-shell extract).

Must not import ``bluesky_bot_v2``. The bot remains the composition root and
wires :class:`HealthPorts` (recovery callables).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Sequence

logger = logging.getLogger(__name__)


@dataclass
class HealthPorts:
    """Dependencies for :class:`HealthService` (pragmatic recovery ports)."""

    get_http_session: Callable[[], Any]
    get_memory_mb: Callable[[], float]
    get_successful_posts: Callable[[], Sequence[Any]]
    get_likes_given: Callable[[], int]
    cleanup_content_hashes: Callable[[], None]
    cleanup_commented_posts: Callable[[], None]
    reinit_http: Callable[[], Awaitable[Any]]
    create_emergency_post: Callable[[], Awaitable[Any]]
    authenticate: Callable[[], Awaitable[bool]]
    save_memory: Callable[[], None]


class HealthService:
    """Bot health checks, auto-recovery actions, and emergency recovery."""

    def __init__(self, ports: HealthPorts) -> None:
        self._ports = ports

    async def health_monitor(self) -> Dict[str, Any]:
        """Run health checks and optional auto-recovery."""
        logger.info("🏥 Запуск мониторинга здоровья бота...")

        health_status: Dict[str, Any] = {
            "overall_health": "healthy",
            "last_activity": None,
            "network_status": "unknown",
            "memory_usage": 0,
            "api_connectivity": {},
            "recommendations": [],
            "auto_recovery_actions": [],
        }

        try:
            network_checks = await self._check_network_connectivity()
            health_status["api_connectivity"] = network_checks
            health_status["network_status"] = (
                "healthy" if network_checks.get("bluesky_api", False) else "degraded"
            )

            health_status["memory_usage"] = self._ports.get_memory_mb()

            last_activity = await self._check_last_activity()
            health_status["last_activity"] = last_activity

            issues = await self._analyze_potential_issues(health_status)
            recovery_actions = await self._perform_auto_recovery(issues)
            health_status["auto_recovery_actions"] = recovery_actions

            if len(issues) == 0:
                health_status["overall_health"] = "healthy"
            elif len(issues) <= 2:
                health_status["overall_health"] = "warning"
            else:
                health_status["overall_health"] = "critical"

            logger.info(f"🏥 Мониторинг завершен: {health_status['overall_health']}")
            for action in recovery_actions:
                logger.info(f"🔧 Восстановление: {action}")

            return health_status

        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга здоровья: {e}")
            health_status["overall_health"] = "error"
            return health_status

    async def _check_network_connectivity(self) -> Dict[str, bool]:
        """Probe external API endpoints."""
        connectivity = {
            "bluesky_api": False,
            "pollinations_ai": False,
            "openai_api": False,
            "general_internet": False,
        }

        async def check_endpoint(url: str, timeout: int = 10) -> bool:
            try:
                session = self._ports.get_http_session()
                if not session:
                    return False
                async with session.get(url, timeout=timeout) as response:
                    return response.status < 500
            except Exception as e:
                logger.debug(f"Сетевая проверка {url}: {e}")
                return False

        try:
            tasks = [
                check_endpoint("https://rooter.us-west.host.bsky.network/"),
                check_endpoint("https://text.pollinations.ai/"),
                check_endpoint("https://api.openai.com/"),
                check_endpoint("https://httpbin.org/get"),
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            connectivity["bluesky_api"] = (
                results[0] if isinstance(results[0], bool) else False
            )
            connectivity["pollinations_ai"] = (
                results[1] if isinstance(results[1], bool) else False
            )
            connectivity["openai_api"] = (
                results[2] if isinstance(results[2], bool) else False
            )
            connectivity["general_internet"] = (
                results[3] if isinstance(results[3], bool) else False
            )
        except Exception as e:
            logger.warning(f"⚠️ Ошибка проверки сети: {e}")

        return connectivity

    async def _check_last_activity(self) -> Dict[str, Any]:
        """Inspect recent posting / engagement activity."""
        try:
            now = datetime.now()
            activity: Dict[str, Any] = {
                "last_post_hours_ago": None,
                "last_engagement_hours_ago": None,
                "cycles_without_posts": 0,
                "stuck_in_cycle": False,
            }

            posts = self._ports.get_successful_posts()
            if posts:
                last_post_time = max(
                    post.get("timestamp", now) for post in list(posts)[-10:]
                )
                if isinstance(last_post_time, str):
                    last_post_time = datetime.fromisoformat(
                        last_post_time.replace("Z", "+00:00")
                    )
                activity["last_post_hours_ago"] = (
                    now - last_post_time
                ).total_seconds() / 3600

            if self._ports.get_likes_given() > 0:
                activity["last_engagement_hours_ago"] = 0
            else:
                activity["last_engagement_hours_ago"] = 2

            if activity["last_post_hours_ago"] and activity["last_post_hours_ago"] > 6:
                activity["stuck_in_cycle"] = True

            return activity
        except Exception as e:
            logger.warning(f"⚠️ Ошибка проверки активности: {e}")
            return {}

    async def _analyze_potential_issues(
        self, health_status: Dict[str, Any]
    ) -> List[str]:
        """Map health snapshot → issue tags."""
        issues: List[str] = []

        if not health_status["api_connectivity"].get("bluesky_api", False):
            issues.append("bluesky_api_unavailable")

        if not health_status["api_connectivity"].get("general_internet", False):
            issues.append("internet_connectivity_issue")

        if health_status["memory_usage"] > 400:
            issues.append("high_memory_usage")

        activity = health_status.get("last_activity") or {}
        if activity.get("stuck_in_cycle", False):
            issues.append("stuck_in_posting_cycle")

        last_post_hours = activity.get("last_post_hours_ago")
        if last_post_hours is not None and last_post_hours > 8:
            issues.append("no_posts_long_time")

        return issues

    async def _perform_auto_recovery(self, issues: List[str]) -> List[str]:
        """Run recovery actions for detected issues."""
        recovery_actions: List[str] = []

        try:
            if "high_memory_usage" in issues:
                self._ports.cleanup_content_hashes()
                self._ports.cleanup_commented_posts()
                recovery_actions.append("memory_cleanup_performed")

            if "no_posts_long_time" in issues:
                try:
                    emergency_post = await self._ports.create_emergency_post()
                    if emergency_post:
                        recovery_actions.append("emergency_post_created")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось создать экстренный пост: {e}")

            if "stuck_in_posting_cycle" in issues:
                recovery_actions.append("cycle_state_reset")

            if (
                "bluesky_api_unavailable" in issues
                or "internet_connectivity_issue" in issues
            ):
                try:
                    await self._ports.reinit_http()
                    recovery_actions.append("http_session_reinitialized")
                except Exception as e:
                    logger.warning(
                        f"⚠️ Не удалось переинициализировать HTTP сессию: {e}"
                    )

        except Exception as e:
            logger.error(f"❌ Ошибка автовосстановления: {e}")
            recovery_actions.append(f"recovery_error: {str(e)}")

        return recovery_actions

    async def emergency_recovery(self) -> bool:
        """Full emergency recovery: save, cleanup, reinit HTTP, re-auth."""
        logger.warning("🚨 ЭКСТРЕННОЕ ВОССТАНОВЛЕНИЕ АКТИВИРОВАНО")

        try:
            self._ports.save_memory()
            logger.info("💾 Состояние сохранено")

            self._ports.cleanup_content_hashes()
            self._ports.cleanup_commented_posts()
            logger.info("🧹 Кэши очищены")

            await self._ports.reinit_http()
            logger.info("🔄 HTTP сессия переинициализирована")

            auth_success = await self._ports.authenticate()
            if not auth_success:
                logger.error("❌ Не удалось восстановить аутентификацию")
                return False

            logger.info("✅ Экстренное восстановление завершено успешно")
            return True

        except Exception as e:
            logger.error(f"❌ Критическая ошибка экстренного восстановления: {e}")
            return False
