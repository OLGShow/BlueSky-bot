#!/usr/bin/env python3
"""AuthService — session restore + credential login (thin-shell extract).

Must not import ``bluesky_bot_v2``. The bot remains the composition root and
wires :class:`AuthPorts`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from api_incident_log import record_incident
from resilience_service import classify_error

logger = logging.getLogger(__name__)


@dataclass
class AuthPorts:
    """Bot-like ports for :class:`AuthService` (pragmatic callables)."""

    ensure_http: Callable[[], Awaitable[Any]]
    load_session: Callable[[], Optional[str]]
    clear_session: Callable[[], None]
    save_session: Callable[[str], None]
    restore_login: Callable[[str], Awaitable[Any]]
    credential_login: Callable[[], Awaitable[Any]]
    export_session_string: Callable[[], Optional[str]]
    set_authenticated: Callable[[bool], None]
    get_handle: Callable[[], str]


class AuthService:
    """Session-first auth: restore persisted session, fallback to login."""

    def __init__(self, ports: AuthPorts) -> None:
        self._ports = ports

    def persist_session(self) -> None:
        """Export client session string and save via session store."""
        try:
            ss = self._ports.export_session_string()
            if ss:
                self._ports.save_session(ss)
        except Exception as e:
            logger.warning(f"⚠️ Не удалось сохранить сессию: {e}")

    async def authenticate(self, force_login: bool = False) -> bool:
        """Session-first auth: restore persisted session, fallback to login.

        Login path is expected to use ``retry_atproto`` (RETRY-003) via the
        injected ``restore_login`` / ``credential_login`` ports.
        """
        await self._ports.ensure_http()
        handle = self._ports.get_handle()

        if not force_login:
            saved = self._ports.load_session()
            if saved:
                try:
                    profile = await self._ports.restore_login(saved)
                    self._ports.set_authenticated(True)
                    self.persist_session()
                    logger.info(
                        f"✅ Сессия восстановлена для "
                        f"{getattr(profile, 'handle', handle)}"
                    )
                    return True
                except Exception as e:
                    record_incident("auth", "restore_login", exc=e)
                    logger.warning(
                        f"⚠️ Не удалось восстановить сессию: {e}. Переход к login."
                    )
                    self._ports.clear_session()

        try:
            await self._ports.credential_login()
            self._ports.set_authenticated(True)
            self.persist_session()
            logger.info(f"✅ Успешная авторизация: {handle}")
            return True
        except Exception as e:
            record_incident("auth", "credential_login", exc=e)
            ec = classify_error(e)
            logger.error(f"❌ Ошибка авторизации ({ec.value}): {e}")
            return False
