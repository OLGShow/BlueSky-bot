#!/usr/bin/env python3
"""Daily report + dry-run flush aggregation — Phase 7 / DRY-001.

Thin façade over ``growth_engine.generate_daily_report`` / ``save_daily_report``.

Import rules:
- Must not import ``bluesky_bot_v2``.

API health (W1-004): call ``write_api_health_daily_report()`` after the daily
flush, or pass it as ``DailyReportingFacade(..., _api_health=write_api_health_daily_report)``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Union

logger = logging.getLogger(__name__)


def write_api_health_daily_report(
    path_jsonl: str = "reports/api_incidents.jsonl",
    out_dir: Union[str, Path] = "reports",
    *,
    day: Any = None,
) -> Optional[Path]:
    """Write ``api_health_daily_YYYY-MM-DD.json``; never raises into callers.

    Bot wiring (later)::

        from daily_reporting import write_api_health_daily_report
        write_api_health_daily_report()

        # or inject into the façade:
        DailyReportingFacade(
            _generate=...,
            _save=...,
            _api_health=write_api_health_daily_report,
        )
    """
    try:
        from api_incident_log import write_api_health_daily

        return write_api_health_daily(path_jsonl, out_dir=out_dir, day=day)
    except Exception as exc:
        logger.warning("api health daily write failed: %s", exc)
        return None


def write_followers_cohort_daily_report(
    report: Mapping[str, Any],
    *,
    out_dir: Union[str, Path] = "reports",
) -> Optional[Path]:
    """Write ``followers_daily_YYYY-MM-DD.json`` from cohort apply report (W1-006)."""
    try:
        from follower_analytics import write_followers_daily_report

        return write_followers_daily_report(report, out_dir=out_dir)
    except Exception as exc:
        logger.warning("followers daily write failed: %s", exc)
        return None


@dataclass
class DailyReportingFacade:
    """Aggregate daily report save + AB persist + optional dry-run flush."""

    _generate: Callable[[Mapping[str, Any], Any, Mapping[str, Any]], Dict[str, Any]]
    _save: Callable[[Dict[str, Any]], None]
    _api_health: Optional[Callable[[], Any]] = None

    def generate_and_save(
        self,
        session_stats: Mapping[str, Any],
        memory: Any,
        config: Mapping[str, Any],
        *,
        ab_results: Any = None,
        dry_run: bool = False,
        dry_run_log: Any = None,
    ) -> Dict[str, Any]:
        """Build report, persist file, sync AB onto memory, flush dry-run log."""
        report = self._generate(session_stats, memory, config)
        self._save(report)
        if ab_results is not None and hasattr(memory, "ab_results"):
            memory.ab_results = ab_results
        if dry_run and dry_run_log is not None and hasattr(dry_run_log, "save"):
            dry_run_log.save()
        if self._api_health is not None:
            try:
                self._api_health()
            except Exception as exc:
                logger.warning("daily_reporting api_health hook failed: %s", exc)
        return report
