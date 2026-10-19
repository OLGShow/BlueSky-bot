# Plan: Audit CRITICAL/HIGH Remediation (Oct 2026)

**Created:** 2026-10-19 13:04
**Orchestration:** orch-2026-10-19-13-04-audit-remediation
**Status:** ✅ Completed
**Goal:** Remediate verified CRITICAL and HIGH findings from the multi-agent project audit (security / PR-review / deep audit), with focused code fixes, tests, and clear deferrals for false positives.
**Sources:**
- `reports/security_agent_report.md`
- `reports/pr_review_agent_report.md`
- `reports/audit_agent_report.md`
**Total Tasks:** 9
**Priority:** Critical / High (P0–P1)
**Mode:** documentation plan (`enabled.plans = true`)

## Constraints

- Max ~10 tasks (this plan: 9)
- Prefer root source of truth (`bluesky_bot_v2.py`, `state_service.py`, `log_sanitizer.py`, `.dockerignore`)
- Do **not** edit packaging stage copies (`packaging/_stage/`, `opt/bluesky-bot/` duplicates) unless a deploy path requires it
- Reuse existing `log_sanitizer.py`, `SingleInstanceLock`, `ActivityBudget`, `SessionStore` atomic save
- VERIFY before “fixing” claimed hardcoded credentials
- Behavior-preserving where possible; harden without rewriting the God-class monolith

## Tasks Overview

1. **VER-001** → Triage credentials / session race / rate-limit claims (FP vs real gaps)
2. **SEC-001** → Fix Bandit B324 weak MD5 in content hash (`usedforsecurity=False` or stronger non-crypto hash)
3. **SEC-002** → Close `.dockerignore` sensitive-context gaps + hermetic tests
4. **HTTP-001** → Centralize `aiohttp.ClientSession` ensure/create/close (no leaks on recreate)
5. **SESS-001** → SessionStore concurrency hardening (file lock defense-in-depth)
6. **LOG-001** → Extend log sanitizer for OpenRouter keys; confirm filter wiring
7. **VAL-001** → Input validation for outbound user-facing text (posts/comments)
8. **TEST-001** → Unit/hermetic tests for SEC/HTTP/LOG/VAL/SESS changes
9. **DOC-001** → Document deferred/FP findings + remediation notes for audit trail

## Dependencies Graph

```
VER-001 ──┬──→ SEC-001 ──────────────┐
          ├──→ SEC-002 ──────────────┤
          ├──→ HTTP-001 ─────────────┼──→ TEST-001 ──→ DOC-001
          ├──→ SESS-001 ─────────────┤
          ├──→ LOG-001 ──────────────┤
          └──→ VAL-001 ──────────────┘
```

- **VER-001 first** (narrows scope; may cancel or shrink later tasks if already mitigated)
- SEC-001, SEC-002, HTTP-001, SESS-001, LOG-001, VAL-001 can run **in parallel** after VER-001
- **TEST-001** after implementation tasks
- **DOC-001** last

## Progress (updated by orchestrator)

- ✅ VER-001: Triage credentials / session / rate-limit claims — **Completed 2026-10-19**
  - **#1 session race → partial (real residual)** — `SingleInstanceLock` wraps `main()` bot run; `SessionStore` atomic save + chmod 0o600 present; no cross-process file lock → **SESS-001** (later completed).
  - **#2 hardcoded keys → FP (+ small fail-fast gap closed)** — no literal API keys in source; creds via `os.getenv` only; placeholder/`your-` gate in `main()`; `__init__` raises on empty. Closed gap: empty/whitespace `BLUESKY_HANDLE`/`BLUESKY_PASSWORD` now fail-fast in `main()` + strip in `__init__` (no interactive prompt).
  - **#4 auth rate limits → FP / already mitigated** — `authenticate()` classifies `ErrorClass.RATE_LIMIT` with exponential backoff `60 * 2^n` (max 3 retries). **Deferred — no code change.**
  - **#8 API rate limiting → FP / already mitigated** — `ActivityBudget` gates posts (`create_scheduled_post`) and EngagementService like/repost/follow; budget logged each cycle. `maintain_rate_limits()` is unused stub (non-blocking). **Deferred — no code change.**
  - Downstream: SEC/HTTP/SESS/LOG/VAL proceeded as planned; #4/#8 did not spawn new tasks.
- ✅ SEC-001: Bandit B324 MD5 content-hash fix — **Completed** (`usedforsecurity=False`)
- ✅ SEC-002: `.dockerignore` gap closure — **Completed**
- ✅ HTTP-001: ClientSession lifecycle centralization — **Completed** (`_ensure_http_session`)
- ✅ SESS-001: SessionStore file-lock hardening — **Completed** (best-effort lock)
- ✅ LOG-001: OpenRouter key sanitization — **Completed** (`sk-or-v1-`)
- ✅ VAL-001: Outbound content validation — **Completed** (`validate_outbound_text`)
- ✅ TEST-001: Tests for remediation — **Completed** (65 OK, 2 skipped)
- ✅ DOC-001: Deferred/FP documentation — **Completed**
  - Report: `ai_docs/develop/reports/2026-10-19-audit-critical-high-remediation-implementation.md`
  - Issue: `ai_docs/develop/issues/ISS-001-audit-deferred-fp-findings.md`

## Architecture Decisions

- **Content hashing is non-security:** MD5 used only for duplicate detection → prefer `hashlib.md5(..., usedforsecurity=False)` over migrating memory hash format (avoids invalidating existing `published_content_hashes`).
- **Single process assumed:** `SingleInstanceLock` remains primary multi-instance guard; SessionStore file lock is belt-and-suspenders for edge entrypoints.
- **HTTP session:** one shared `ClientSession` per bot lifetime; all recreate paths must `close()` first and go through a single `_ensure_http_session()` helper (timeouts/connector from `_create_http_session`).
- **Secrets:** env-only; no vault in this cycle; fail-fast on placeholder Bluesky creds; OpenRouter optional with explicit warning (legacy Pollinations).
- **Sanitizer reuse:** extend `log_sanitizer.py` patterns; do not invent a second sanitizer.

## Deferred / False-Positive Findings

| Finding | Severity | Disposition | Why |
|--------|----------|-------------|-----|
| Hardcoded API keys (audit #2) | CRITICAL | **FP (VER-001 confirmed)** | No literal keys in source; env-only. Placeholder + empty/whitespace fail-fast in `main()`; strip + empty raise in `__init__`. No vault/prompt. |
| Session race (audit #1) | CRITICAL | **Resolved — SESS-001** | Was partial after VER-001; best-effort SessionStore file lock completed in-cycle. |
| Auth rate-limit handling (audit #4) | HIGH | **FP / deferred (VER-001)** | `authenticate()` RATE_LIMIT backoff `60 * 2^n`, max 3 retries — complete. No further code. |
| Lack of API rate limiting (audit #8) | HIGH | **FP / deferred (VER-001)** | `ActivityBudget` on post + like/repost/follow write paths. Unused `maintain_rate_limits` stub is non-blocking. No further code. |
| Secrets leakage in logs (audit #5) | HIGH | **Resolved — LOG-001** | OpenRouter `sk-or-v1-` pattern added to `log_sanitizer.py`. |
| aiohttp resource leak (audit #7) | HIGH | **Resolved — HTTP-001** | `_ensure_http_session()` + close-before-recreate. |
| HTTP session create error handling (audit #3) | HIGH | **Resolved — HTTP-001** | Create failures logged via helper; recreate paths consistent. |
| Input validation (audit #6) | HIGH | **Resolved — VAL-001** | `validate_outbound_text` at publish/comment boundary. |
| Bandit B324 MD5 | HIGH | **Resolved — SEC-001** | `usedforsecurity=False` on content hash. |
| `.dockerignore` sensitive files | HIGH (PR) | **Resolved — SEC-002** | Certs/keys/`credentials.json`/`secrets/`/`packaging/_stage` excluded; SEC-003 tests green. |
| pip-audit timeout | n/a | **Deferred** | Ops/CI timeout, not an app code bug; keep non-blocking. |
| MD5 in `opt/` / `packaging/_stage/` | HIGH (scan) | **Deferred** | Packaging copies; fix root SoT only unless deploy copies from root automatically. |
| Audit MEDIUM #9–#15, LOW #16–#18 | M/L | **Deferred** | Out of this orchestration cycle (cache eviction already partial; session encryption; SSRF; health checks; log path config). |

## Implementation Notes for Workers

- Source of truth files: `bluesky_bot_v2.py`, `state_service.py`, `log_sanitizer.py`, `.dockerignore`, `tests/test_dockerignore_sec003.py`
- Prefer small helpers over large refactors
- Follow existing test style in `tests/` (unittest, hermetic, no live network)
- Russian user-facing logs may stay; new code comments in English OK if matching file style

---

## Task Details

### VER-001: Triage credentials / session race / rate-limit claims
- **Priority:** Critical
- **Complexity:** Simple
- **Audit IDs:** audit #1, #2, #4, #8
- **Files:** `bluesky_bot_v2.py` (read + small fail-fast tweaks only), notes in plan Progress / issue stub if FP confirmed
- **Approach:**
  - Confirm no literal API keys in source; document env-only + placeholder gate in `main()`
  - If empty `BLUESKY_PASSWORD` / missing handle slip through, add fail-fast (do not prompt interactively)
  - Confirm `SingleInstanceLock` wraps bot run; note residual SessionStore risk → SESS-001
  - Confirm auth backoff + `ActivityBudget` usage on write paths; mark audit #4/#8 deferred if complete
- **Acceptance:**
  - Written triage result in plan (FP / partial / real) for #1, #2, #4, #8
  - Any real fail-fast gap for Bluesky creds fixed
  - No interactive vault/prompt added
- **Dependencies:** None

### SEC-001: Fix Bandit B324 MD5 content hash
- **Priority:** High
- **Complexity:** Simple
- **Audit IDs:** security Bandit B324 (~line 607)
- **Files:** `bluesky_bot_v2.py` (`_generate_content_hash`)
- **Approach:**
  - Change to `hashlib.md5(..., usedforsecurity=False)` **or** equivalent Bandit-safe non-crypto API
  - Do not change hash algorithm if it would invalidate existing memory hashes (prefer `usedforsecurity=False`)
  - Root file only
- **Acceptance:**
  - Bandit B324 cleared for root `bluesky_bot_v2.py` content hash
  - Duplicate-detection behavior unchanged for existing hashes
- **Dependencies:** VER-001 (soft)

### SEC-002: Close `.dockerignore` sensitive-context gaps
- **Priority:** High
- **Complexity:** Simple
- **Audit IDs:** PR-review HIGH `.dockerignore`
- **Files:** `.dockerignore`, `tests/test_dockerignore_sec003.py`
- **Approach:**
  - Gap inventory vs current SEC-003 patterns: add missing high-value excludes if absent, e.g. `**/credentials.json`, `**/*.pem`, `**/*.key`, `secrets/`, `packaging/_stage/`, `**/*secret*`, without excluding required build sources (`bluesky_bot_v2.py`, `requirements.txt`, `env.example`, `Dockerfile`)
  - Update `REQUIRED_PATTERNS` / `MUST_EXCLUDE` in existing hermetic test
  - Do not break `MUST_NOT_EXCLUDE`
- **Acceptance:**
  - New patterns present; `python -m unittest tests.test_dockerignore_sec003` passes
  - Required app sources still not excluded
- **Dependencies:** VER-001 (soft)

### HTTP-001: Centralize aiohttp ClientSession lifecycle
- **Priority:** High
- **Complexity:** Moderate
- **Audit IDs:** audit #3, #7
- **Files:** `bluesky_bot_v2.py` (`_create_http_session`, `authenticate`, RSS/image/diagnostics recreate sites, recovery, `shutdown`)
- **Approach:**
  - Add `_ensure_http_session()` that creates via `_create_http_session` if missing/closed; wrap create in try/except with log + re-raise or safe failure
  - Replace bare `aiohttp.ClientSession()` at recreate sites (~authenticate, RSS fetch, upload_image, diagnostics) with `_ensure_http_session()`
  - On reinit (recovery/emergency): always `await close()` then create via helper
  - Keep `shutdown()` closing session (and AI adapter sessions)
- **Acceptance:**
  - No bare `ClientSession()` construction left in bot class (helper only)
  - Recreate paths close previous session
  - Create failures logged; bot does not silently continue with `None` session on critical paths without clear error
- **Dependencies:** VER-001 (soft)

### SESS-001: SessionStore concurrency hardening
- **Priority:** Critical (defense-in-depth)
- **Complexity:** Moderate
- **Audit IDs:** audit #1
- **Files:** `state_service.py` (`SessionStore`), optionally `tests/test_session_store_chmod_sec004.py` or new test
- **Approach:**
  - Add best-effort exclusive file lock around `save`/`load`/`clear` (Windows + POSIX); if lock unavailable, keep current atomic write behavior and log once
  - Do not remove `SingleInstanceLock` or chmod 0o600 behavior
  - Keep atomic temp+move write
- **Acceptance:**
  - Concurrent save/load does not corrupt JSON under a simple threaded/multiprocess smoke test where feasible
  - Existing chmod 0o600 tests still pass
  - Lock failure is non-fatal (best-effort) with warning
- **Dependencies:** VER-001

### LOG-001: Extend log sanitizer for OpenRouter keys
- **Priority:** High
- **Complexity:** Simple
- **Audit IDs:** audit #5
- **Files:** `log_sanitizer.py`, confirm wiring in `bluesky_bot_v2.py`
- **Approach:**
  - Extend `_TOKEN_RE` (or add pattern) for `sk-or-v1-...` OpenRouter keys
  - Confirm `SanitizingFilter` still attached to root handlers
  - Do not log raw keys in new code paths
- **Acceptance:**
  - Sample log line containing `sk-or-v1-` + long secret is masked by filter
  - Existing handle/email/JWT masking still works
- **Dependencies:** VER-001 (soft)

### VAL-001: Outbound content validation
- **Priority:** High
- **Complexity:** Moderate
- **Audit IDs:** audit #6
- **Files:** prefer small helper in `content_service.py` or dedicated tiny module; call from publish/comment paths in `bluesky_bot_v2.py`
- **Approach:**
  - Validate/sanitize outbound text: strip NUL/control chars (keep newlines/tabs as needed), enforce Bluesky-safe max length, reject empty after strip
  - Apply at publish boundary (scheduled posts / comments), not every internal string
  - No HTML injection framework needed (ATProto text); focus on length + control chars + obvious unsafe payloads
- **Acceptance:**
  - Invalid content (empty / over-long / control-heavy) rejected or truncated safely before API call
  - Valid normal posts unchanged
- **Dependencies:** VER-001 (soft)

### TEST-001: Tests for remediation
- **Priority:** High
- **Complexity:** Moderate
- **Audit IDs:** covers SEC-001, SEC-002, HTTP-001, LOG-001, VAL-001, SESS-001
- **Files:** `tests/` (new and/or extend existing)
- **Approach:**
  - Hermetic unit tests: MD5 `usedforsecurity` / hash helper; sanitizer OpenRouter; content validator; SessionStore lock smoke; dockerignore patterns
  - Optional static check that bot source has no bare `ClientSession()` outside helper (regex/AST) if practical
  - Run via `python -m unittest` / project verify script if present
- **Acceptance:**
  - New/updated tests pass locally
  - Existing SEC-003 / SEC-004 tests still pass
- **Dependencies:** SEC-001, SEC-002, HTTP-001, SESS-001, LOG-001, VAL-001

### DOC-001: Document deferred/FP findings
- **Priority:** Medium
- **Complexity:** Simple
- **Audit IDs:** all deferred rows above
- **Files:** `ai_docs/develop/issues/` (one ISS file for deferred audit items) and/or short note under `ai_docs/develop/audits/`; plan Progress updated
- **Approach:**
  - Record FP/deferred table with rationale (pip-audit, packaging copies, MEDIUM/LOW, confirmed FPs from VER-001)
  - No secrets in docs
- **Acceptance:**
  - Issue or audit note exists listing deferred items and why
  - Plan Progress reflects completed/deferred status
- **Dependencies:** TEST-001 (and VER-001 outcomes)

## Recommended Subagent Routing

| Task | Primary | Then |
|------|---------|------|
| VER-001 | worker / senior-reviewer skim | — |
| SEC-001, SEC-002, LOG-001 | worker | test-writer |
| HTTP-001, SESS-001, VAL-001 | worker | test-writer |
| TEST-001 | test-writer → test-runner | debugger if fail |
| DOC-001 | documenter | — |
| After each impl task | reviewer (lightweight) | — |

## Next Steps

Execute with: `/orchestrate execute orch-2026-10-19-13-04-audit-remediation`
