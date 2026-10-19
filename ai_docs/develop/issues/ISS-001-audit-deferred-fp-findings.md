# Issue: Audit Deferred / False-Positive Findings (Oct 2026 Remediation)

**ID:** ISS-001
**Created:** 2026-10-19
**Severity:** Mixed (documented FP / deferred Medium–Low / ops)
**Status:** Open (tracking — CRITICAL/HIGH done; partial MEDIUM via MED-001)
**Orchestration:** orch-2026-10-19-13-04-audit-remediation (+ backlog MED-001)
**Task:** DOC-001 / MED-001
**Report:** [2026-10-19-audit-critical-high-remediation-implementation.md](../reports/2026-10-19-audit-critical-high-remediation-implementation.md)
**Plan:** [2026-10-19-audit-critical-high-remediation.md](../plans/2026-10-19-audit-critical-high-remediation.md), [2026-10-19-backlog-followup.md](../plans/2026-10-19-backlog-followup.md)

## Description

Audit trail for findings from the multi-agent Oct 2026 audit that were confirmed as false positives, partially addressed then completed in-cycle, or explicitly deferred outside the CRITICAL/HIGH remediation orchestration. No secrets are recorded here.

## Disposition Table

| Finding | Severity | Disposition | Why / Notes |
|--------|----------|-------------|-------------|
| Hardcoded API keys (audit #2) | CRITICAL | **FP (VER-001)** | No literal keys in source; creds via `os.getenv` only. Placeholder + empty/whitespace fail-fast in `main()`; strip + empty raise in `__init__`. No vault/prompt. |
| Session race (audit #1) | CRITICAL | **Resolved in-cycle (SESS-001)** | Was partial after VER-001 (`SingleInstanceLock` + atomic save + chmod 0o600). Residual closed with best-effort SessionStore file lock. |
| Auth rate-limit handling (audit #4) | HIGH | **FP / deferred** | `authenticate()` already classifies `ErrorClass.RATE_LIMIT` with exponential backoff `60 * 2^n`, max 3 retries. No further code. |
| Lack of API rate limiting (audit #8) | HIGH | **FP / deferred** | `ActivityBudget` gates posts and EngagementService like/repost/follow. Unused `maintain_rate_limits()` stub is non-blocking. No further code. |
| Secrets leakage in logs (audit #5) | HIGH | **Resolved in-cycle (LOG-001)** | Was partial (`SanitizingFilter` wired; gap was OpenRouter `sk-or-v1-`). Pattern extended in `log_sanitizer.py`. |
| aiohttp resource leak (audit #7) | HIGH | **Resolved in-cycle (HTTP-001)** | `_ensure_http_session()` + close-before-recreate. |
| HTTP session create error handling (audit #3) | HIGH | **Resolved in-cycle (HTTP-001)** | Create failures logged via helper; consistent recreate paths. |
| Input validation (audit #6) | HIGH | **Resolved in-cycle (VAL-001)** | `validate_outbound_text` at publish/comment boundary. |
| Bandit B324 MD5 | HIGH | **Resolved in-cycle (SEC-001)** | `usedforsecurity=False` on content hash. |
| `.dockerignore` sensitive files | HIGH (PR) | **Resolved in-cycle (SEC-002)** | Added certs/keys/`credentials.json`/`secrets/`/`packaging/_stage` patterns; hermetic tests green. |
| pip-audit timeout | n/a | **Deferred** | Ops/CI timeout, not an app code bug; keep non-blocking. |
| MD5 in `opt/` / `packaging/_stage/` | HIGH (scan) | **Resolved (SYNC-001)** | `opt/bluesky-bot/` synced from root SoT (incl. `usedforsecurity=False`, `http_session.py`, `url_safety.py`). Root remains SoT. |
| SSRF / unrestricted outbound ([S5] / MEDIUM) | Medium | **Resolved (MED-001)** | `url_safety.py`: http/https allowlist; block private/link-local/loopback/metadata IPs + blocked hostnames; reject `file://` / odd schemes / userinfo. Wired into RSS fetch, image upload, rich-post metadata/gallery, RSS `add_candidate`, post formatter image fetch. Hermetic tests: `tests/test_url_safety_med001.py`. |
| In-memory cache bound (MEDIUM) | Medium | **Resolved (MED-001)** | Soft caps via `_trim_in_memory_caches()` (engagement sets / dict caches / `content_cache` / trend snippets); called before periodic memory save. |
| Lightweight health/status (MEDIUM) | Medium | **Resolved (MED-001)** | Sync `get_status()` (local, no network). Existing async `health_monitor()` unchanged. |
| Session encryption at rest | Medium | **Deferred** | Explicitly out of MED-001; session file remains `0o600` only (no encryption). |
| Log path config redesign | Medium | **Deferred** | Still deferred. |
| Remaining MEDIUM / LOW #16–#18 | M/L | **Deferred** | Not in MED-001 scope. |

## Why Not Fixed Now (deferred rows)

- **pip-audit timeout:** CI/ops configuration; does not change application security posture when treated as non-blocking.
- **Packaging/`opt` MD5 copies:** Closed via SYNC-001 (`opt/bluesky-bot/` mirrored from root).
- **Session encryption at rest:** Deferred by design in MED-001 (prefer SSRF + cache/status wins); chmod `0o600` remains the session file control.
- **Log path config / remaining MEDIUM–LOW:** Explicitly out of MED-001 max 2–3 fixes; prioritize in a later plan.

## Impact

- In-cycle CRITICAL/HIGH remediations are complete and tested.
- MED-001 closed SSRF + cache bounds + lightweight status; session encryption and other MEDIUM/LOW remain tech debt.
- FP rows should not be re-filed as open CRITICAL/HIGH without new evidence.

## Proposed Follow-ups

1. Session encryption at rest (if threat model requires it beyond `0o600`).
2. ~~Sync packaging stage / `opt/` copies from root SoT~~ — done (SYNC-001).
3. Investigate pip-audit CI timeout separately (non-app) — TOOL-001 hygiene applied; keep monitoring.
4. Remaining MEDIUM/LOW audit items (log path config, etc.).

## Related Files

- `url_safety.py` (new)
- `tests/test_url_safety_med001.py` (new)
- `bluesky_bot_v2.py`
- `bluesky_rich_posts.py`
- `bluesky_post_formatter.py`
- `rss_source_manager.py`
- `state_service.py`
- `log_sanitizer.py`
- `content_service.py`
- `.dockerignore`
- Sources: `reports/security_agent_report.md`, `reports/pr_review_agent_report.md`, `reports/audit_agent_report.md`

## Related

- Orchestration: orch-2026-10-19-13-04-audit-remediation
- Tasks: VER-001, DOC-001, MED-001 (and resolved SEC/HTTP/SESS/LOG/VAL)
