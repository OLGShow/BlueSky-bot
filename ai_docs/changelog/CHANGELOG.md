# Changelog

## [Unreleased]

### Added
- Phase 7 leftovers: `heartbeat_monitor.py`, `engagement_cache_sync.py`, `smart_engagement.py`, `daily_reporting.py` (HB/CACHE/ENG/DRY)
- Hermetic suites: `test_heartbeat_monitor_hb001`, `test_engagement_cache_sync_cache001`, `test_smart_engagement_eng001`, `test_daily_reporting_dry001`
- Soft-fail strategies + duplicate fallback (`soft_fail_posts.py`, SOFT-001…004) + content dedup façade (`content_publish_state.py`, STATE-001)
- Hermetic suites: `test_soft_fail_soft002`, `test_content_publish_state_state001` (SEC-001 retargeted to façade)
- Viral/trending strategies (`viral_posts.py`, STRAT-009…011) + Phase 7 slices: `strategy_learning.py` (LEARN-001), `bot_cycle.BotCycleRunner` (CYCLE-001)
- Hermetic suites: `test_viral_strategies_strat010`, `test_strategy_learning_learn001`, `test_bot_cycle_cycle001`
- Strategy families extract — `ImagePostHelper` + dynamic / theme / poll / insight+prediction (`STRAT-004`…`008`); hybrid registry overwrite for remaining default-weight keys
- Hermetic strategy/HTTP/retry suites: `test_image_post_helper_strat004`, `test_dynamic_posts_strat005`, `test_theme_posts_strat006`, `test_quality_poll_strategy_strat007`, `test_insight_posts_strat008`, `test_http_session_http002`, `test_retry_policy_retry003`
- Strategy package `app/strategies/` — `QualityNewsStrategy` + news ports; hybrid registry overwrite for `_create_quality_news_post` (STRAT-001…003)
- Unified quality pipeline (`quality_pipeline.py`) — `QualityPipeline.evaluate` / `regenerate_until_quality` on scheduled post (QUAL-001 / QUAL-002)
- Outbound `RetryPolicy` factory (`OutboundRetryPolicies`) + hermetic retry tests (`tests/test_retry_policy_retry002.py`) (RETRY-001 / RETRY-002)
- Quality pipeline hermetic tests (`tests/test_quality_pipeline_qual002.py`)
- Content ports (`content_ports.py`) — `PromptContextPort` / `BackgroundSchedulerPort` / `ContentPorts`; `ContentService` no longer takes `bot` (CONT-001…004)
- ContentService hermetic port tests (`tests/test_content_ports_cont004.py`) + registry dispatch tests (`tests/test_post_strategies_strat.py`)
- Engagement ports (`engagement_ports.py`) — Protocols for client/ledger/budget/dry-run/stats; `EngagementService` no longer takes `bot` (REF-001 / REF-002)
- Post strategy registry skeleton (`post_strategies.py`) — Protocol + register/get/list; full migration deferred (REF-003)
- ADR: layering, ports, phased God Object decomposition ([2026-10-19-layering-and-ports.md](../develop/architecture/2026-10-19-layering-and-ports.md))
- `opt/README.md` — tracked mirror vs local runtime (LAY-004)
- Follow-up plan: God Object Phase 2+ ([god-object-decomposition-followup.md](../develop/plans/2026-10-19-god-object-decomposition-followup.md))
- Outbound URL safety helper (`url_safety.py`) with SSRF guards on fetch paths (MED-001)
- Extracted HTTP session module (`http_session.py`) — God-class first slice (REF-001)
- Post-deploy hermetic smoke: `verify_bot.py --smoke` / `scripts/smoke_check.py` (SMOKE-001)
- GitHub Actions CI unittest workflow (`.github/workflows/ci.yml`) — CI-001
- Outbound content validation (`validate_outbound_text`) at publish/comment boundary (VAL-001)
- Best-effort SessionStore file lock for concurrent save/load/clear (SESS-001)
- Centralized aiohttp `_ensure_http_session()` lifecycle helper (HTTP-001)
- OpenRouter `sk-or-v1-` masking in log sanitizer (LOG-001)
- Hermetic remediation + backlog test suites — 112 OK, 3 skipped (TEST-001)
- Audit deferred/FP tracking: [ISS-001](../develop/issues/ISS-001-audit-deferred-fp-findings.md)

### Changed
- Formatter / rich_posts use injected shared `ClientSession` (HTTP-002); Phase 6 shared-HTTP complete for AI + post formatters
- ATProto + media upload paths use `retry_atproto` / `retry_media_upload` via `RetryPolicy.execute` (RETRY-003); Phase 4 outbound retry complete for catalogued I/O
- OpenRouter / Pollinations use injected shared `ClientSession` + `RetryPolicy.execute`; RSS GET via `_http_get_text_with_retry` (RETRY-002 / HTTP-001)
- Packaging sync includes `strategies/` package dir + `quality_pipeline.py` under `opt/` (8 strategy modules mirrored)
- Full `post_strategies` registry registration + `create_scheduled_post` dispatch via `weighted_entries` / `resolve` (STRAT-001 / STRAT-002); news + dynamic/theme/poll/insight/prediction/viral extracted; soft-fail leftovers deferred
- Packaging sync includes `bot_cycle.py` / `strategy_learning.py` + `strategies/` under `opt/`
- Packaging sync includes `content_ports.py` (and prior `engagement_ports.py` / `post_strategies.py`) mirrors under `opt/`
- Single systemd unit SoT (`systemd/bluesky-bot.service`); `build-deb.sh` copies unit via `cp` (LAY-003)
- `opt/bluesky-bot/env.example` aligned with root SoT (LAY-002)
- Bad/placeholder Bluesky creds now exit process with code 1 (EXIT-001)
- In-memory cache soft caps + sync `get_status()` (MED-001)
- `opt/bluesky-bot/` synced from root SoT incl. new helpers (SYNC-001)
- Agents README: OpenRouter secret setup + smoke/CI notes (PRA-001 / TOOL-001)
- Content hash MD5 calls use `usedforsecurity=False` (SEC-001 / Bandit B324)
- `.dockerignore` excludes credentials, PEM/key files, secrets dirs, packaging stage (SEC-002)
- Bluesky empty/whitespace handle/password fail-fast in `main()` (VER-001)

### Fixed
- List-strategy fallback newlines — `_build_list_fallback` used literal `\\n`; now real newlines (app + opt); see STRAT-006 in [implementation report](../develop/reports/2026-10-19-strat-families-http-retry-implementation.md)
- Remaining strategy families + HTTP-002 + RETRY-003 (`orch-2026-10-19-17-34-strat-families`) — smoke 2/2; unittest 246 OK (3 skipped); viral + Phase 7 deferred; see [implementation report](../develop/reports/2026-10-19-strat-families-http-retry-implementation.md)
- STRAT-003 + RetryPolicy / Quality / Shared HTTP cycle (`orch-2026-10-19-17-06-strat003-io`) — smoke 2/2; unittest 193 OK (3 skipped); see [implementation report](../develop/reports/2026-10-19-strat003-retry-quality-http-implementation.md)
- God Object Phase 2+ ContentService ports + strategy registry wiring (`orch-2026-10-19-15-06-godobj-p2`) — see [implementation report](../develop/reports/2026-10-19-god-object-phase2-content-strategies-implementation.md)
- Layout hygiene Stages 1–4: untracked root `__pycache__/`, env.example drift, systemd SoT/heredoc, opt docs (`orch-2026-10-19-14-33-layout-godobj`) — see [implementation report](../develop/reports/2026-10-19-layout-and-god-object-prep-implementation.md)
- Backlog follow-up P0–P2 cycle (`orch-2026-10-19-13-45-backlog-followup`) — see [implementation report](../develop/reports/2026-10-19-backlog-followup-implementation.md)
- Audit CRITICAL/HIGH remediation cycle (`orch-2026-10-19-13-04-audit-remediation`) — see [implementation report](../develop/reports/2026-10-19-audit-critical-high-remediation-implementation.md)
