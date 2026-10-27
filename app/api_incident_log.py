"""Append-only API incident log (JSONL) for ATProto / engagement failures.

Wave 1.2 (W1-002/W1-004): normalized events, error classifier, daily summary.
Does not import bluesky_bot_v2 — call sites wire this in W1-003.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)

DEFAULT_PATH = "reports/api_incidents.jsonl"
DEFAULT_REPORTS_DIR = "reports"
MESSAGE_TRUNCATE = 160
TOP_STAGES_LIMIT = 10

# Stable error_class values (telemetry taxonomy for Wave 1.2).
ERROR_CLASS_429 = "429"
ERROR_CLASS_AUTH_REQUIRED = "AuthRequired"
ERROR_CLASS_ACCOUNT_SUSPENDED = "AccountSuspended"
ERROR_CLASS_FORBIDDEN = "Forbidden"
ERROR_CLASS_NETWORK = "network"
ERROR_CLASS_OTHER = "other"

_TOKEN_RE = re.compile(
    r"(sk-or-v1-[A-Za-z0-9]{20,})"
    r"|(sk-[A-Za-z0-9_-]{20,})"
    r"|([A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4})"
    r"|(eyJ[A-Za-z0-9_-]{30,})"
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_HANDLE_RE = re.compile(r"@([A-Za-z0-9_-]+\.bsky\.social)")

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


def _mask(match: re.Match) -> str:
    val = match.group(0)
    if len(val) <= 8:
        return "***"
    return val[:4] + "***" + val[-3:]


def sanitize_message(text: Any) -> str:
    """Short, secret-safe message suitable for JSONL."""
    raw = "" if text is None else str(text)
    raw = _TOKEN_RE.sub(_mask, raw)
    raw = _EMAIL_RE.sub(_mask, raw)
    raw = _HANDLE_RE.sub(_mask, raw)
    raw = " ".join(raw.split())
    if len(raw) > MESSAGE_TRUNCATE:
        return raw[:MESSAGE_TRUNCATE]
    return raw


def _is_secret_key(key: str) -> bool:
    lowered = str(key).lower()
    return any(frag in lowered for frag in _SECRET_KEY_FRAGMENTS)


def sanitize_extra(value: Any, *, _depth: int = 0) -> Any:
    """Drop secrets and truncate nested values for optional ``extra``."""
    if _depth > 6:
        return "<max_depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return sanitize_message(value)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            sk = str(key)
            if _is_secret_key(sk):
                continue
            out[sk] = sanitize_extra(item, _depth=_depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [sanitize_extra(item, _depth=_depth + 1) for item in value[:50]]
    return sanitize_message(value)


def _exc_blob(exc_or_text: Union[BaseException, str, None]) -> str:
    if exc_or_text is None:
        return ""
    if isinstance(exc_or_text, BaseException):
        name = type(exc_or_text).__name__
        return f"{name} {exc_or_text}".lower()
    return str(exc_or_text).lower()


def classify_error(exc_or_text: Union[BaseException, str, None]) -> str:
    """Map exception / text to a stable incident ``error_class``.

    Classes: ``429``, ``AuthRequired``, ``AccountSuspended``, ``Forbidden``,
    ``network``, ``other``. AccountTakedown / Suspended collapse to
    ``AccountSuspended``.
    """
    blob = _exc_blob(exc_or_text)
    if not blob.strip():
        return ERROR_CLASS_OTHER

    if any(
        p in blob
        for p in (
            "accounttakedown",
            "account_takedown",
            "takedown",
            "accountsuspended",
            "account_suspended",
            "suspended",
        )
    ):
        return ERROR_CLASS_ACCOUNT_SUSPENDED

    if any(
        p in blob
        for p in ("429", "rate limit", "ratelimit", "too many requests")
    ):
        return ERROR_CLASS_429

    if any(
        p in blob
        for p in ("authrequired", "auth_required", "401", "unauthorized")
    ):
        return ERROR_CLASS_AUTH_REQUIRED

    if any(p in blob for p in ("forbidden", "403")):
        return ERROR_CLASS_FORBIDDEN

    if any(
        p in blob
        for p in (
            "timeout",
            "timed out",
            "connectionerror",
            "connection reset",
            "connection refused",
            "connecterror",
            "network",
            "dns",
            "gaierror",
            "broken pipe",
            "reset by peer",
            "temporarily unavailable",
            "name or service not known",
        )
    ):
        return ERROR_CLASS_NETWORK

    return ERROR_CLASS_OTHER


def _classify_status(status: Optional[int]) -> Optional[str]:
    if status is None:
        return None
    try:
        code = int(status)
    except (TypeError, ValueError):
        return None
    if code == 429:
        return ERROR_CLASS_429
    if code == 401:
        return ERROR_CLASS_AUTH_REQUIRED
    if code == 403:
        return ERROR_CLASS_FORBIDDEN
    return None


def build_incident_event(
    stage: str,
    op: str,
    *,
    status: Optional[int] = None,
    error_class: Optional[str] = None,
    message: Optional[str] = None,
    exc: Optional[BaseException] = None,
    did: Optional[str] = None,
    uri: Optional[str] = None,
    extra: Optional[dict] = None,
    ts: Optional[str] = None,
) -> dict[str, Any]:
    """Build a normalized incident event dict (does not write)."""
    resolved_class = error_class
    if not resolved_class:
        # Prefer exception/text taxonomy (AccountSuspended etc.), then status.
        from_exc = classify_error(exc) if exc is not None else ERROR_CLASS_OTHER
        from_status = _classify_status(status)
        if from_exc != ERROR_CLASS_OTHER:
            resolved_class = from_exc
        elif from_status is not None:
            resolved_class = from_status
        else:
            resolved_class = from_exc

    if message is None and exc is not None:
        message = f"{type(exc).__name__}: {exc}"
    msg = sanitize_message(message) if message is not None else ""

    event: dict[str, Any] = {
        "ts": ts or _utc_now_iso(),
        "stage": str(stage),
        "op": str(op),
        "error_class": str(resolved_class),
        "message": msg,
    }
    if status is not None:
        try:
            event["status"] = int(status)
        except (TypeError, ValueError):
            pass
    if did:
        event["did"] = str(did)[:128]
    if uri:
        event["uri"] = sanitize_message(uri)
    if extra:
        event["extra"] = sanitize_extra(extra)
    return event


def append_incident(path: str, event: dict) -> None:
    """Append one JSONL line. Never raises into callers."""
    try:
        target = str(path or DEFAULT_PATH)
        parent = os.path.dirname(os.path.abspath(target))
        if parent:
            os.makedirs(parent, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False, default=str) + "\n"
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(line)
    except Exception as exc:
        logger.warning("api_incident_log write failed: %s", exc)


def record_incident(
    stage: str,
    op: str,
    *,
    exc: Optional[BaseException] = None,
    status: Optional[int] = None,
    message: Optional[str] = None,
    error_class: Optional[str] = None,
    did: Optional[str] = None,
    uri: Optional[str] = None,
    extra: Optional[dict] = None,
    path: Optional[str] = None,
) -> None:
    """Convenience: build + append an incident. Never raises into callers."""
    try:
        event = build_incident_event(
            stage,
            op,
            status=status,
            error_class=error_class,
            message=message,
            exc=exc,
            did=did,
            uri=uri,
            extra=extra,
        )
        append_incident(path or DEFAULT_PATH, event)
    except Exception as err:
        logger.warning("api_incident_log record_incident failed: %s", err)


def _coerce_utc_day(day: Optional[Union[str, date, datetime]]) -> date:
    """Normalize ``day`` to a UTC calendar date (default: today UTC)."""
    if day is None:
        return datetime.now(timezone.utc).date()
    if isinstance(day, datetime):
        if day.tzinfo is None:
            return day.replace(tzinfo=timezone.utc).date()
        return day.astimezone(timezone.utc).date()
    if isinstance(day, date):
        return day
    text = str(day).strip()
    if not text:
        return datetime.now(timezone.utc).date()
    if "T" in text:
        parsed = _event_utc_day(text)
        if parsed is not None:
            return parsed
    return date.fromisoformat(text[:10])


def _event_utc_day(ts: Any) -> Optional[date]:
    """Extract UTC date from an incident ``ts`` value; None if unparseable."""
    if ts is None:
        return None
    try:
        raw = str(ts).strip()
        if not raw:
            return None
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).date()
    except (TypeError, ValueError, OSError):
        return None


def _top_stages_for_class(
    by_stage_error_class: dict[str, dict[str, int]],
    error_class: str,
    *,
    limit: int = TOP_STAGES_LIMIT,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for stage, classes in by_stage_error_class.items():
        count = int(classes.get(error_class, 0) or 0)
        if count > 0:
            rows.append({"stage": stage, "count": count})
    rows.sort(key=lambda r: (-r["count"], r["stage"]))
    return rows[: max(0, int(limit))]


def summarize_incidents(
    path: str,
    day: Optional[Union[str, date, datetime]] = None,
) -> dict[str, Any]:
    """Build counts by ``stage × error_class`` for one UTC day from JSONL.

    Returns a dict shaped for ``api_health_daily_*.json`` (without writing)::

        {
          "date": "2026-10-27",
          "source": "reports/api_incidents.jsonl",
          "total": 12,
          "skipped_lines": 0,
          "by_stage_error_class": {"follow": {"429": 3}, "like": {"429": 5}},
          "by_error_class": {"429": 8},
          "by_stage": {"follow": 3, "like": 5},
          "top_stages_429": [{"stage": "like", "count": 5}, ...],
          "top_stages_AccountSuspended": [{"stage": "auth", "count": 1}, ...],
        }
    """
    target_day = _coerce_utc_day(day)
    source = str(path or DEFAULT_PATH)
    by_stage_error: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    by_error_class: dict[str, int] = defaultdict(int)
    by_stage: dict[str, int] = defaultdict(int)
    total = 0
    skipped = 0

    try:
        with open(source, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    skipped += 1
                    continue
                if not isinstance(event, dict):
                    skipped += 1
                    continue
                event_day = _event_utc_day(event.get("ts"))
                if event_day is None or event_day != target_day:
                    continue
                stage = str(event.get("stage") or "unknown")
                err_class = str(
                    event.get("error_class") or ERROR_CLASS_OTHER
                )
                by_stage_error[stage][err_class] += 1
                by_error_class[err_class] += 1
                by_stage[stage] += 1
                total += 1
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("api_incident_log summarize read failed: %s", exc)

    nested = {
        stage: dict(sorted(classes.items()))
        for stage, classes in sorted(by_stage_error.items())
    }
    return {
        "date": target_day.isoformat(),
        "source": source,
        "total": total,
        "skipped_lines": skipped,
        "by_stage_error_class": nested,
        "by_error_class": dict(sorted(by_error_class.items())),
        "by_stage": dict(sorted(by_stage.items())),
        "top_stages_429": _top_stages_for_class(nested, ERROR_CLASS_429),
        "top_stages_AccountSuspended": _top_stages_for_class(
            nested, ERROR_CLASS_ACCOUNT_SUSPENDED
        ),
    }


def write_api_health_daily(
    path_jsonl: str,
    out_dir: Union[str, Path] = DEFAULT_REPORTS_DIR,
    *,
    day: Optional[Union[str, date, datetime]] = None,
) -> Path:
    """Write ``reports/api_health_daily_YYYY-MM-DD.json`` for a UTC day.

    Invokable from the bot after the daily report flush, e.g.::

        from api_incident_log import write_api_health_daily
        write_api_health_daily("reports/api_incidents.jsonl", out_dir="reports")

    Or via ``daily_reporting.write_api_health_daily_report()`` /
    ``DailyReportingFacade(..., _api_health=write_api_health_daily_report)``.
    """
    summary = summarize_incidents(path_jsonl, day=day)
    reports = Path(out_dir)
    reports.mkdir(parents=True, exist_ok=True)
    out_path = reports / f"api_health_daily_{summary['date']}.json"
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False, default=str)
        handle.write("\n")
    logger.info("api health daily saved: %s (total=%s)", out_path, summary["total"])
    return out_path
