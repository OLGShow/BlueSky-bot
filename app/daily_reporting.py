#!/usr/bin/env python3
"""Daily report + dry-run flush aggregation — Phase 7 / DRY-001.

Thin façade over ``growth_engine.generate_daily_report`` / ``save_daily_report``.

Import rules:
- Must not import ``bluesky_bot_v2``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, MutableMapping, Optional


@dataclass
class DailyReportingFacade:
    """Aggregate daily report save + AB persist + optional dry-run flush."""

    _generate: Callable[[Mapping[str, Any], Any, Mapping[str, Any]], Dict[str, Any]]
    _save: Callable[[Dict[str, Any]], None]

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
        return report
