# Changelog

## [Unreleased]

### Added
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
- Bad/placeholder Bluesky creds now exit process with code 1 (EXIT-001)
- In-memory cache soft caps + sync `get_status()` (MED-001)
- `opt/bluesky-bot/` synced from root SoT incl. new helpers (SYNC-001)
- Agents README: OpenRouter secret setup + smoke/CI notes (PRA-001 / TOOL-001)
- Content hash MD5 calls use `usedforsecurity=False` (SEC-001 / Bandit B324)
- `.dockerignore` excludes credentials, PEM/key files, secrets dirs, packaging stage (SEC-002)
- Bluesky empty/whitespace handle/password fail-fast in `main()` (VER-001)

### Fixed
- Backlog follow-up P0–P2 cycle (`orch-2026-10-19-13-45-backlog-followup`) — see [implementation report](../develop/reports/2026-10-19-backlog-followup-implementation.md)
- Audit CRITICAL/HIGH remediation cycle (`orch-2026-10-19-13-04-audit-remediation`) — see [implementation report](../develop/reports/2026-10-19-audit-critical-high-remediation-implementation.md)
