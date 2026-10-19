# Changelog

## [Unreleased]

### Added
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
- OpenRouter / Pollinations use injected shared `ClientSession` + `RetryPolicy.execute`; RSS GET via `_http_get_text_with_retry` (RETRY-002 / HTTP-001)
- Packaging sync includes `strategies/` package dir + `quality_pipeline.py` under `opt/`
- Full `post_strategies` registry registration + `create_scheduled_post` dispatch via `weighted_entries` / `resolve` (STRAT-001 / STRAT-002); news family extracted (STRAT-003); other families still deferred
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
- STRAT-003 + RetryPolicy / Quality / Shared HTTP cycle (`orch-2026-10-19-17-06-strat003-io`) — smoke 2/2; unittest 193 OK (3 skipped); see [implementation report](../develop/reports/2026-10-19-strat003-retry-quality-http-implementation.md)
- God Object Phase 2+ ContentService ports + strategy registry wiring (`orch-2026-10-19-15-06-godobj-p2`) — see [implementation report](../develop/reports/2026-10-19-god-object-phase2-content-strategies-implementation.md)
- Layout hygiene Stages 1–4: untracked root `__pycache__/`, env.example drift, systemd SoT/heredoc, opt docs (`orch-2026-10-19-14-33-layout-godobj`) — see [implementation report](../develop/reports/2026-10-19-layout-and-god-object-prep-implementation.md)
- Backlog follow-up P0–P2 cycle (`orch-2026-10-19-13-45-backlog-followup`) — see [implementation report](../develop/reports/2026-10-19-backlog-followup-implementation.md)
- Audit CRITICAL/HIGH remediation cycle (`orch-2026-10-19-13-04-audit-remediation`) — see [implementation report](../develop/reports/2026-10-19-audit-critical-high-remediation-implementation.md)
