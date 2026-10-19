#!/usr/bin/env python3
"""Publish ports for ScheduledPostPublisher — create_scheduled_post extract.

Narrow callables / values the publisher needs. The bot remains the composition
root and wires concrete adapters via ``_build_publish_ports()``.

Import rules:
- Must not import ``bluesky_bot_v2`` or application services.
- Stdlib / typing only — keeps the ports → bot edge acyclic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Awaitable, Callable, List, Optional, Sequence


@dataclass
class PublishPorts:
    """Dependencies injected into :class:`ScheduledPostPublisher`.

    Keep pragmatic: plain callables / flags, not a deep Protocol hierarchy.
    """

    # --- Gates ---
    safety_status: Callable[[], Any]
    can_spend_post: Callable[[], bool]
    spend_post: Callable[[], None]

    # --- Daily post limit ---
    get_daily_post_count: Callable[[], int]
    set_daily_post_count: Callable[[int], None]
    get_max_posts_per_day: Callable[[], int]
    get_last_post_date: Callable[[], Optional[date]]
    set_last_post_date: Callable[[date], None]

    # --- Strategy arms (config ∩ registry) ---
    get_strategy_arm_keys: Callable[[], List[str]]

    # --- Memory / recent posts ---
    get_successful_posts: Callable[[], Sequence[Any]]

    # --- Format pick (FormatBandit or ABEngine fallback) ---
    has_format_bandit: Callable[[], bool]
    pick_format_bandit: Callable[[Sequence[str], Sequence[str]], str]
    record_format_pick: Callable[[str], None]
    get_format_bandit_learner: Callable[[], Any]
    pick_ab_format: Callable[[], str]
    get_prompt_suffix: Callable[[str], str]
    log_pick: Callable[..., None]

    set_current_ab_format: Callable[[str], None]
    set_current_ab_suffix: Callable[[str], None]
    get_dry_run_format_label: Callable[[], str]

    # --- Trend radar (telemetry only) ---
    get_trend_timeline_snippets: Callable[[], Sequence[str]]
    get_trend_rss_headlines: Callable[[], Sequence[str]]
    get_topic_of_day: Callable[[Sequence[str]], Any]

    # --- Strategy pick + resolve ---
    pick_strategy: Callable[[Sequence[str], Sequence[str]], str]
    record_strategy_pick: Callable[[str], None]
    get_policy_learner: Callable[[], Any]
    set_current_strategy_key: Callable[[str], None]
    get_current_strategy_key: Callable[[], Optional[str]]
    resolve_strategy: Callable[[str], Awaitable[Any]]

    # --- Quality pipeline ---
    quality_pipeline: Any
    set_quality_gate_regen_mode: Callable[[bool], None]
    apply_quality_result: Callable[[Any, Any], None]

    is_duplicate: Callable[[str, Any, Any], bool]
    create_fallback: Callable[[], Awaitable[Any]]
    evaluate_quality: Callable[[Any], bool]

    enforce_text_limit: Callable[[Any], Any]

    # --- Publish / dry-run ---
    dry_run: bool
    dry_run_log: Callable[..., None]
    send_post: Callable[..., Awaitable[Any]]

    mark_published: Callable[[str, Any, Any], None]
    bump_posts_created: Callable[[], None]
    generate_content_hash: Callable[[str, Any, Any], str]
    append_successful_post: Callable[[dict], None]
    append_viral_post: Callable[[dict], None]
    schedule_checks: Callable[[str], None]

    refresh_followers_at_publish: Callable[[], Awaitable[Optional[int]]]
    record_ab_impression: Callable[[str], None]

    bump_errors: Callable[[], None]
