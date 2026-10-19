# Plan: Critical Audit Remediation (S1/S2/A1 + S3/S4)

**Created:** 2026-09-15 23:28
**Orchestration:** orch-2026-09-15-23-28-audit-remediation
**Goal:** Remediate CRITICAL audit findings (secrets hygiene, Docker bake risk, first A1 slice) plus highest-impact High security fixes that are safely automatable in-repo (S3, S4).
**Source:** `ai_docs/develop/audits/2026-09-15-full-project-audit.md`
**Total Tasks:** 7
**Priority:** Critical / P0–P1
**Mode:** documentation plan (`enabled.plans = true`)

## Constraints

- Max 10 tasks (this plan: 7)
- No full God-class rewrite — only one incremental A1 boundary
- DO NOT put real secrets in docs
- DO NOT force-push / history rewrite as automated step — mark as **manual user action**
- Prefer behavior-preserving changes; S3/S4 may add hardening guards only
- In-repo only; credential rotation itself is operator-side

## Tasks Overview

1. **SEC-001** → Expand `.gitignore` secret/state coverage — [S1][S6]
2. **SEC-002** → Write rotation + history-purge runbook (manual steps) — [S1]
3. **SEC-003** → Harden `.dockerignore` + Dockerfile so nested secrets never enter image — [S2]
4. **SEC-004** → `SessionStore` save/load hardening (`chmod 600`) — [S3]
5. **SEC-005** → Gate / replace unsafe `pickle.load` migration — [S4]
6. **REF-001** → Extract thin PostStrategy helper (A1 first slice, no behavior change) — [A1][Q1]
7. **VER-001** → Extend `verify_bot.py` checks for ignore patterns + session perms + pickle gate — [S2][S3][S4]

## Dependencies Graph

```
SEC-001 ─┐
         ├─→ SEC-003 ─→ VER-001
SEC-002 ─┘                 ↑
SEC-004 ───────────────────┤
SEC-005 ───────────────────┘
REF-001 (independent; can run parallel with SEC-*)
```

- SEC-001 before SEC-003 recommended (same secret path inventory)
- SEC-002 independent of code (docs)
- SEC-004, SEC-005 independent of each other
- REF-001 independent of security tasks
- VER-001 after SEC-003, SEC-004, SEC-005

## Progress (updated by orchestrator)

- ✅ SEC-001: Expand `.gitignore` secret/state coverage (Completed)
- ✅ SEC-002: Rotation + history-purge runbook (Completed)
- ✅ SEC-003: Docker ignore + COPY hardening (Completed)
- ✅ SEC-004: SessionStore chmod 600 (Completed)
- ✅ SEC-005: Safe pickle migration gate (Completed)
- ✅ REF-001: Thin PostStrategy helper extract (Completed)
- ✅ VER-001: Verification harness updates (Completed)

---

## Task Details

### SEC-001: Expand `.gitignore` secret/state coverage
- **Priority:** Critical
- **Complexity:** Simple
- **Audit IDs:** [S1], [S6] (hygiene only)
- **Files:** `.gitignore`
- **Approach:**
  - Ensure patterns cover nested and export trees: `**/.env`, `**/.env.*`, `**/session.json`, `**/bot_memory.json`, `**/bot_memory.pkl`, `**/action_ledger.jsonl`, and keep/confirm `etc/bluesky-bot/.env`, `opt/bluesky-bot/.env`
  - Do not weaken existing ignores; avoid ignoring needed source under `opt/bluesky-bot/*.py` if those are intentionally tracked — only secret/state globs
  - Confirm `git check-ignore -v` (or Windows equivalent) matches sample paths under `etc/` and `opt/`
- **Acceptance:** Nested `.env` / `session.json` / memory files under `etc/` and `opt/` match ignore rules; no real secret values written into the repo.
- **Out of scope:** History purge, force-push, deleting live local secret files

### SEC-002: Document credential rotation + git-history purge (manual)
- **Priority:** Critical
- **Complexity:** Simple
- **Audit IDs:** [S1]
- **Files:** `ai_docs/develop/plans/` sibling or `ai_docs/develop/` security runbook — prefer `ai_docs/develop/architecture/secret-rotation-runbook.md` OR short section in README + dedicated `ai_docs/develop/issues`/`architecture` doc. **Recommended:** `ai_docs/develop/architecture/2026-09-15-secret-rotation-runbook.md`
- **Approach:**
  - Document that commit `8cfede2` exposed `BLUESKY_PASSWORD`, `BLUESKY_HANDLE`, `OPENAI_API_KEY`
  - Checklist: rotate Bluesky app password; rotate OpenAI (and any other) keys; invalidate old keys; update server `/etc/bluesky-bot/.env` only (no secrets in git)
  - History purge options (BFG / `git filter-repo`) listed as **MANUAL USER STEPS** including force-push and coordinating with collaborators; orchestrator must NOT execute force-push
  - Placeholder env var names only — never paste real values
- **Acceptance:** Runbook exists with rotation checklist + explicit “manual history rewrite / force-push” section; contains no real secrets.
- **Out of scope:** Actually rotating keys or rewriting remote history

### SEC-003: Harden `.dockerignore` + Dockerfile against nested secret bake-in
- **Priority:** Critical
- **Complexity:** Simple–Moderate
- **Audit IDs:** [S2]
- **Files:** `.dockerignore`, `Dockerfile`
- **Approach:**
  - Expand `.dockerignore`: `**/.env`, `**/.env.*`, `**/session.json`, `**/bot_memory.json`, `**/bot_memory.pkl`, `**/action_ledger.jsonl`, entire `etc/`, runtime secret trees under `opt/` (at minimum `opt/**/.env`, `opt/**/session.json`, `opt/**/bot_memory*`, `opt/**/venv/`), plus other state files already listed at root
  - Prefer excluding `etc/` wholesale from build context
  - Dockerfile: keep `COPY requirements.txt` then narrow app copy if feasible (e.g. explicit module list) OR rely on comprehensive `.dockerignore` so `COPY . .` cannot include secrets; document runtime env via env-file / mounts, not build args with secrets
  - Do not bake secrets via `ENV`/`ARG`
- **Acceptance:** A dry-check (script or `verify_bot` assertion) proves ignored paths include nested `etc/.../.env` and `opt/.../session.json`; image build context cannot contain those files.
- **Out of scope:** Rebuilding/pushing production images; rotating keys possibly baked in past images (mention in SEC-002)

### SEC-004: SessionStore file permission hardening
- **Priority:** High
- **Complexity:** Simple
- **Audit IDs:** [S3]
- **Files:** `state_service.py` (`SessionStore.save`); optionally mirror in `opt/bluesky-bot/state_service.py` only if that tree is a deploy duplicate that must stay in sync — prefer fixing canonical root module and noting opt drift as follow-up if out of scope
- **Approach:**
  - After successful atomic write/`shutil.move`, call `os.chmod(self.path, 0o600)` (best-effort on Windows: ignore `OSError` / no-op where unsupported)
  - Optionally set restrictive mode on temp file before move when platform allows
  - No encryption / keyring in this task (future work)
- **Acceptance:** On POSIX, newly saved `session.json` is mode `600`; load/save round-trip in `verify_bot` still passes; no session content logged.
- **Out of scope:** Encrypt-at-rest, OS keyring migration

### SEC-005: Gate or replace unsafe `pickle.load`
- **Priority:** High
- **Complexity:** Moderate
- **Audit IDs:** [S4]
- **Files:** `state_service.py` (`_migrate_pickle`)
- **Approach (prefer safest automatable):**
  - Default: refuse pickle migration unless explicit env flag e.g. `ALLOW_PICKLE_MIGRATION=1`
  - When allowed: verify file is regular file, owned by current UID (POSIX), size under hard cap, then `pickle.load`; after success keep existing archive-as-`.migrated` behavior; prefer deleting or refusing re-read of live `.pkl`
  - If flag unset and only pickle exists: log clear warning and start fresh (or fail closed — choose fail-closed with log if bot cannot run without memory; prefer **warn + fresh** to match current failure path, documented)
  - Prefer JSON-only going forward; do not introduce new pickle writes
- **Acceptance:** Without flag, `pickle.load` is not called; with flag + safe checks, migration still works; unit/verify coverage for both paths.
- **Out of scope:** Full schema redesign [A9]

### REF-001: A1 first slice — thin PostStrategy helper (no behavior change)
- **Priority:** Critical (architecture debt reduction)
- **Complexity:** Moderate
- **Audit IDs:** [A1] (incremental), [Q1]
- **Files:** `bluesky_bot_v2.py` (and optionally tiny new `post_strategy_helpers.py` if extract is cleaner)
- **Approach:**
  - **Do NOT** rewrite the 3700-line class
  - Extract one coherent, behavior-preserving helper used by 2–3 nearly identical `_create_quality_*` methods that already funnel through `_create_post_with_image_generation` (e.g. theme pick → structured prompt → fallback list → image post)
  - Prefer parameterized factory / shared `_quality_theme_post(...)` reducing copy-paste; leave dissimilar strategies (`tip` via dynamic_generator, news/RSS) untouched if they diverge
  - No wiring of CircuitBreakers in this orchestration (that is [A4] and changes runtime behavior) — deferred
- **Acceptance:** At least two strategy methods delegate to the helper; public bot cycle / strategy selection unchanged; smoke import or existing verify path still passes; diff is reviewable (< ~150 LOC net churn preferred).
- **Out of scope:** Full bounded-context split, DIP on services [A2], wiring CircuitBreakers [A4]

### VER-001: Extend verification for secret-hygiene + session + pickle
- **Priority:** High
- **Complexity:** Simple
- **Audit IDs:** [S2], [S3], [S4] (regression nets)
- **Files:** `verify_bot.py` (root; sync `opt/` copy only if required by deploy)
- **Approach:**
  - Strengthen existing `.dockerignore` test to assert nested patterns / `etc/` exclusion
  - Assert `.gitignore` covers nested `.env` / session / memory globs
  - SessionStore test: after save, if POSIX, check `stat.st_mode & 0o777 == 0o600`
  - Pickle: assert migration skipped without allow-flag; optional temp pickle path with flag
- **Acceptance:** `python verify_bot.py` (or documented subset) passes on developer machine; new assertions fail if ignore/hardening regresses.
- **Out of scope:** Full `tests/` package [Q2]

---

## Architecture Decisions

1. **S1 split:** In-repo = ignore hygiene + runbook; operator = rotate + history purge (manual).
2. **S2:** Prefer comprehensive `.dockerignore` + optional narrower COPY; never build-arg secrets.
3. **A1:** First slice = PostStrategy helper (Q1-aligned), not CircuitBreaker wiring (behavior change / A4).
4. **S4:** Fail closed on pickle by default (env-gated), JSON remains source of truth.
5. **Canonical code:** Prefer root modules (`state_service.py`, `bluesky_bot_v2.py`, `verify_bot.py`); call out `opt/bluesky-bot/` drift as non-blocking unless a task explicitly syncs.

## Risks

| Risk | Mitigation |
|------|------------|
| Force-push wipes collaborator work | Manual-only; runbook warns to coordinate |
| Narrow Dockerfile COPY misses modules | Prefer ignore-based fix first; list required `.py` if narrowing |
| Pickle gate breaks legacy hosts | Document `ALLOW_PICKLE_MIGRATION=1` one-shot then delete `.pkl` |
| Strategy extract changes post text | Keep prompts/fallbacks byte-identical; only structure moves |
| Windows chmod no-op | Best-effort; verify on Linux CI/server |

## Out of Scope (this orchestration)

- [S5] SSRF allowlists
- [A2][A3][A4][A5] architecture High items (except A1 first slice)
- Full God-class decomposition
- Actual credential rotation / git filter-repo / force-push
- Encrypt session at rest

## Implementation Notes for Workers

- Project root: `G:\cursor\BlueSky-bot`
- Audit source: `ai_docs/develop/audits/2026-09-15-full-project-audit.md`
- After SEC-003: mention in PR/report that previously built images should be treated as compromised until rebuilt + keys rotated (pointer to SEC-002)
- Russian user-facing docs OK if matching repo README language; code/comments follow existing style
