#!/usr/bin/env python3
"""Heartbeat file write + stale check — Phase 7 / HB-001.

Owns ``bot_heartbeat.txt`` format consumed by ``bot_monitor.check_heartbeat``.
Does **not** touch ``state_service.SingleInstanceLock.heartbeat``.

Import rules:
- Must not import ``bluesky_bot_v2``.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_HEARTBEAT_FILE = "bot_heartbeat.txt"
DEFAULT_STALE_SECONDS = 900  # 15 minutes (bot hang warning)
MONITOR_WARN_SECONDS = 900
MONITOR_CRITICAL_SECONDS = 1200  # 20 minutes (monitor fail)


class HeartbeatMonitor:
    """Write / read bot activity heartbeat file."""

    __slots__ = ("path",)

    def __init__(self, path: str = DEFAULT_HEARTBEAT_FILE) -> None:
        self.path = path

    def update(
        self,
        *,
        status: str = "active",
        now: Optional[datetime] = None,
        pid: Optional[int] = None,
    ) -> datetime:
        """Write ISO timestamp, PID, and status. Returns stamped time."""
        stamped = now or datetime.now()
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(f"{stamped.isoformat()}\n")
                f.write(f"PID: {pid if pid is not None else os.getpid()}\n")
                f.write(f"Status: {status}\n")
        except Exception as e:
            logger.warning("⚠️ Не удалось обновить heartbeat: %s", e)
        return stamped

    def read_last(self) -> Optional[datetime]:
        """Return last heartbeat timestamp, or ``None`` if missing/unreadable."""
        try:
            if not os.path.exists(self.path):
                return None
            with open(self.path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if not lines:
                return None
            return datetime.fromisoformat(lines[0].strip())
        except Exception as e:
            logger.warning("⚠️ Ошибка чтения heartbeat: %s", e)
            return None

    def is_stale(
        self,
        threshold_seconds: float = DEFAULT_STALE_SECONDS,
        *,
        now: Optional[datetime] = None,
    ) -> bool:
        """True when heartbeat older than threshold (bot hang check)."""
        try:
            last = self.read_last()
            if last is None:
                return False
            clock = now or datetime.now()
            age = (clock - last).total_seconds()
            if age > threshold_seconds:
                logger.warning(
                    "⚠️ Потенциальное зависание: последний heartbeat %.1f минут назад",
                    age / 60.0,
                )
                return True
            return False
        except Exception as e:
            logger.warning("⚠️ Ошибка проверки зависания: %s", e)
            return False

    def monitor_status(
        self,
        *,
        warn_seconds: float = MONITOR_WARN_SECONDS,
        critical_seconds: float = MONITOR_CRITICAL_SECONDS,
        now: Optional[datetime] = None,
    ) -> Tuple[bool, str]:
        """CLI/monitor-shaped status: ``(ok_or_warn, message)``.

        Parity with ``bot_monitor.check_heartbeat`` thresholds.
        """
        if not os.path.exists(self.path):
            return False, "Файл heartbeat не найден"
        try:
            last = self.read_last()
            if last is None:
                return False, "Файл heartbeat пуст"
            clock = now or datetime.now()
            age = (clock - last).total_seconds()
            if age > critical_seconds:
                return False, f"Heartbeat устарел на {age / 60.0:.1f} минут"
            if age > warn_seconds:
                return True, f"ПРЕДУПРЕЖДЕНИЕ: Heartbeat {age / 60.0:.1f} минут назад"
            return True, f"OK: Последний heartbeat {age / 60.0:.1f} минут назад"
        except Exception as e:
            return False, f"Ошибка чтения heartbeat: {e}"
