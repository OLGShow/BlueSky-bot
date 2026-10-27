#!/usr/bin/env python3
"""
Shared aiohttp ClientSession lifecycle helpers (HTTP-001 / REF-001).

Sole construction point for the bot's shared session; ensure closes before
recreate; close for shutdown.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Mapping, Optional, Protocol, runtime_checkable

import aiohttp

from http_identity import get_user_agent

logger = logging.getLogger(__name__)


@runtime_checkable
class HttpSessionConsumer(Protocol):
    """Narrow port: adapters that accept an injected shared ClientSession."""

    def set_http_session(self, session: Optional[aiohttp.ClientSession]) -> None:
        ...


def create_http_session(
    config: Optional[Mapping[str, Any]] = None,
) -> aiohttp.ClientSession:
    """Create HTTP session with protective timeouts (sole ClientSession ctor).

    Sets a sticky User-Agent from ``http_identity`` (config or defaults).
    Does **not** attach proxy — use ``http_identity.resolve_proxy_url`` for
    aiohttp only when explicitly enabled.
    """
    try:
        timeout = aiohttp.ClientTimeout(
            total=60,      # Общий таймаут запроса
            connect=10,    # Таймаут соединения
            sock_read=30   # Таймаут чтения данных
        )

        session = aiohttp.ClientSession(
            timeout=timeout,
            connector=aiohttp.TCPConnector(
                limit=20,           # Максимум 20 одновременных соединений
                limit_per_host=5,   # Максимум 5 на хост
                ttl_dns_cache=300,  # Кэш DNS на 5 минут
                use_dns_cache=True,
                keepalive_timeout=30
            ),
            headers={"User-Agent": get_user_agent(config)},
        )
        logger.info("🌐 HTTP сессия создана с защитными таймаутами")
        return session
    except Exception as e:
        logger.error(f"❌ Не удалось создать HTTP сессию: {e}")
        raise


async def ensure_http_session(
    session: Optional[aiohttp.ClientSession],
    *,
    force_recreate: bool = False,
    create: Optional[Callable[[], aiohttp.ClientSession]] = None,
) -> aiohttp.ClientSession:
    """Ensure a live shared ClientSession; on recreate — close, then create.

    ``create`` defaults to :func:`create_http_session`. Callers that mutate an
    owner attribute (e.g. bot wrappers) may pass a custom factory that still
    returns the live session.
    """
    create_fn = create or create_http_session
    needs_create = force_recreate or session is None or session.closed

    if needs_create:
        if session is not None and not session.closed:
            try:
                await session.close()
            except Exception as e:
                logger.warning(f"⚠️ Ошибка закрытия HTTP сессии перед пересозданием: {e}")
        session = create_fn()

    if session is None or session.closed:
        raise RuntimeError("HTTP session is unavailable after ensure")

    return session


async def close_http_session(session: Optional[aiohttp.ClientSession]) -> None:
    """Close session if open; log and swallow close errors."""
    if session is None or session.closed:
        return
    try:
        await session.close()
        logger.info("🔒 Основная HTTP сессия закрыта")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка закрытия основной HTTP сессии: {e}")
