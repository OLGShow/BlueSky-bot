"""Append-only agent decision log (JSONL) for strategy/format/engagement picks.

PLRN-012: no secrets/PII — text fields truncated; token-like keys stripped.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_PATH = "reports/agent_decisions.jsonl"
DEFAULT_MAX_LINES = 10000
TEXT_TRUNCATE = 80

_SECRET_KEY_FRAGMENTS = (
    "token",
    "password",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "private_key",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_secret_key(key: str) -> bool:
    lowered = str(key).lower()
    return any(frag in lowered for frag in _SECRET_KEY_FRAGMENTS)


def sanitize_context(value: Any, *, _depth: int = 0) -> Any:
    """Drop secrets and truncate long strings for safe JSONL logging."""
    if _depth > 6:
        return "<max_depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) > TEXT_TRUNCATE:
            return value[:TEXT_TRUNCATE]
        return value
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            sk = str(key)
            if _is_secret_key(sk):
                continue
            out[sk] = sanitize_context(item, _depth=_depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [sanitize_context(item, _depth=_depth + 1) for item in value[:50]]
    return str(value)[:TEXT_TRUNCATE]


class AgentDecisionLog:
    """Append-only JSONL log with line-count rotation (keep last N)."""

    def __init__(
        self,
        path: str = DEFAULT_PATH,
        max_lines: int = DEFAULT_MAX_LINES,
    ):
        self.path = str(path or DEFAULT_PATH)
        self.max_lines = max(1, int(max_lines))

    def log(
        self,
        domain: str,
        action: str,
        arm: str,
        reason: str = "thompson",
        context: Optional[dict] = None,
    ) -> None:
        """Append one decision record. Never raises to callers."""
        entry = {
            "ts": _utc_now_iso(),
            "domain": str(domain),
            "action": str(action),
            "arm": str(arm),
            "reason": str(reason or "thompson"),
            "context": sanitize_context(context or {}),
        }
        try:
            parent = os.path.dirname(os.path.abspath(self.path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(line)
            self._maybe_rotate()
        except Exception as exc:
            logger.warning("AgentDecisionLog write failed: %s", exc)

    def recent(self, n: int = 20) -> list[dict]:
        """Return last N parsed decision records (best-effort)."""
        limit = max(0, int(n))
        if limit == 0 or not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                lines = [ln.strip() for ln in handle if ln.strip()]
        except Exception as exc:
            logger.warning("AgentDecisionLog read failed: %s", exc)
            return []
        out: list[dict] = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def _count_lines(self) -> int:
        if not os.path.exists(self.path):
            return 0
        count = 0
        with open(self.path, "r", encoding="utf-8") as handle:
            for _ in handle:
                count += 1
        return count

    def _maybe_rotate(self) -> None:
        """If file exceeds max_lines, rewrite keeping the last N lines."""
        try:
            if self._count_lines() <= self.max_lines:
                return
            with open(self.path, "r", encoding="utf-8") as handle:
                lines = handle.readlines()
            keep = lines[-self.max_lines :]
            dir_name = os.path.dirname(os.path.abspath(self.path)) or "."
            os.makedirs(dir_name, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.writelines(keep)
                os.replace(tmp, self.path)
            except Exception:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
        except Exception as exc:
            logger.warning("AgentDecisionLog rotate failed: %s", exc)
