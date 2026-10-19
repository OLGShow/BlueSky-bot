# Plan: Backlog Follow-up (P0–P2) — Post-Audit Everything

**Created:** 2026-10-19 13:45
**Orchestration:** orch-2026-10-19-13-45-backlog-followup
**Status:** ✅ Completed
**Goal:** Закрыть весь одобренный пользователем follow-up backlog после CRITICAL/HIGH remediation (`orch-2026-10-19-13-04-audit-remediation`): exit codes, sync packaging SoT, commits, CI, pr-agent, smoke, точечные MEDIUM, первый slice God-class, tooling hygiene.
**Priority:** P0 → P1 → P2 (этот цикл ≤10 задач)
**Mode:** documentation plan (`enabled.plans = true`)
**Sources:**
- User backlog approval («да надо ВСЕ»)
- `ai_docs/develop/issues/ISS-001-audit-deferred-fp-findings.md`
- `ai_docs/develop/audits/2026-09-15-full-project-audit.md` ([S5], MEDIUM notes)
- Prior plan: `ai_docs/develop/plans/2026-10-19-audit-critical-high-remediation.md`

## Constraints

- Max ~10 tasks this cycle (this plan: **10**)
- Root is SoT; `opt/bluesky-bot/` and packaging stage are **explicit sync** targets (SYNC-001)
- Hermetic unit tests for every code change
- Do **not** rewrite entire `bluesky_bot_v2.py` — first extract slice only (REF-001)
- Session encryption at rest: **defer** (too large for this cycle)
- Cannot set GitHub secrets remotely — document `OPENROUTER_API_KEY` setup only
- Commits only when executing GIT-001 (user already approved «всё», including commit); use conventional commits; split as specified
- Russian user — keep docs/plan bilingual or Russian where helpful

## Tasks Overview

| # | ID | Name | Priority | Complexity | Est. |
|---|-----|------|----------|------------|------|
| 1 | EXIT-001 | `sys.exit(1)` on bad Bluesky creds in `main()` | P0 Critical | Simple | 0.5h |
| 2 | SYNC-001 | Sync `opt/bluesky-bot/` (+ packaging stage) from root SoT | P0 Critical | Moderate | 1h |
| 3 | CI-001 | GitHub Actions unittest job on PR/push | P1 High | Simple | 0.75h |
| 4 | PRA-001 | Fix/verify pr-agent workflow + secret docs | P1 High | Simple | 0.75h |
| 5 | SMOKE-001 | Post-deploy smoke / dry-run check | P1 High | Moderate | 1.5h |
| 6 | MED-001 | Top MEDIUM fixes (SSRF + 1–2 easy wins) | P2 Medium | Moderate | 2h |
| 7 | REF-001 | God-class first slice: extract HTTP session helper | P2 Medium | Complex | 2h |
| 8 | TOOL-001 | Dev tooling hygiene (`reports/`, agents README, pip-audit) | P2 Medium | Simple | 0.75h |
| 9 | TEST-001 | Hermetic tests for EXIT/MED/REF/SMOKE changes | P1 High | Moderate | 1.5h |
| 10 | GIT-001 | Clean split commits (remediation / agents / other) | P0 Critical | Simple | 0.5h |

**Total estimated:** ~11h

## Dependencies Graph

```
EXIT-001 ──────────────┐
SYNC-001 (after EXIT + any root SoT deltas) ──┐
CI-001 ───────────────────────────────────────┤
PRA-001 ──────────────────────────────────────┤
SMOKE-001 ────────────────────────────────────┼──→ TEST-001 ──→ GIT-001
MED-001 ──────────────────────────────────────┤
REF-001 ──────────────────────────────────────┤
TOOL-001 ─────────────────────────────────────┘
```

- **EXIT-001** first (tiny, unblocks correct process semantics)
- **SYNC-001** after EXIT-001 (and after MED/REF if those land before sync — prefer sync **once near end before GIT**, or sync twice: mid + final). Recommended: implement all root SoT code tasks first, then **one** SYNC-001 pass before TEST-001/GIT-001
- CI-001, PRA-001, TOOL-001 can run **in parallel** early (docs/config)
- MED-001 and REF-001 can run **in parallel** (different modules if REF extracts new file; coordinate if both touch `bluesky_bot_v2.py`)
- **TEST-001** after EXIT/MED/REF/SMOKE implementations
- **GIT-001** last (after tests green + SYNC done)

### Recommended execution order

1. EXIT-001  
2. CI-001 ∥ PRA-001 ∥ TOOL-001  
3. MED-001 ∥ REF-001 (serialize if both edit same regions of bot)  
4. SMOKE-001  
5. SYNC-001 (full SoT → opt/stage)  
6. TEST-001  
7. GIT-001  

---

## Progress (updated by orchestrator)

- ✅ EXIT-001: sys.exit(1) on bad Bluesky creds (Completed)
- ✅ SYNC-001: Sync opt/packaging from root SoT (Completed)
- ✅ CI-001: GitHub Actions unittest job (Completed)
- ✅ PRA-001: pr-agent workflow + secret docs (Completed)
- ✅ SMOKE-001: Post-deploy smoke/dry-run (Completed)
- ✅ MED-001: Top MEDIUM SSRF + easy wins (Completed)
- ✅ REF-001: Extract HTTP session helper module (Completed)
- ✅ TOOL-001: Dev tooling hygiene (Completed)
- ✅ TEST-001: Hermetic tests for cycle changes (Completed — 112 OK, 3 skipped; smoke exit 0)
- ⏳ GIT-001: Split conventional commits (Pending orchestrator)

**Report:** [ai_docs/develop/reports/2026-10-19-backlog-followup-implementation.md](../reports/2026-10-19-backlog-followup-implementation.md)

---

## Task Details

### EXIT-001: `sys.exit(1)` on bad Bluesky creds
- **Priority:** Critical (P0)
- **Complexity:** Simple
- **Dependencies:** None
- **Files:** `bluesky_bot_v2.py` (`async def main()` ~4010–4037)
- **Context:** Fail-fast already logs and `return`s on missing/placeholder creds → process exits **0**. Same for `SingleInstanceLock` acquire failure.
- **Work:**
  1. On `creds_missing` / `creds_placeholder`: after log lines, `sys.exit(1)` (or raise `SystemExit(1)`). Prefer sync exit before `asyncio` heavy path; if staying inside `async def main`, call `sys.exit(1)` after logs (documented pattern) **or** return a status and exit in `if __name__` — pick one clear pattern consistent with project style.
  2. Optionally also exit **1** when instance lock fails (same bare `return` → 0); include if trivial.
  3. Do **not** change successful-path exit semantics.
- **Acceptance:**
  - Running with empty/placeholder `BLUESKY_HANDLE`/`BLUESKY_PASSWORD` yields process exit code **1**
  - Existing fail-fast unit test (`tests/test_bluesky_creds_failfast_ver001.py`) updated/extended to assert exit code / `SystemExit`
  - Root SoT only in this task (SYNC later)

### SYNC-001: Sync packaging copies from root SoT
- **Priority:** Critical (P0)
- **Complexity:** Moderate
- **Dependencies:** EXIT-001; preferably after MED-001 + REF-001 so one sync captures all
- **Files:** `opt/bluesky-bot/*` mirrored modules; `packaging/_stage/` if present; packaging scripts that copy into stage
- **Context:** Prior cycle fixed root only (MD5/`usedforsecurity`, HTTP session, VAL, creds). ISS-001 deferred packaging drift.
- **Work:**
  1. Identify mirrored modules that diverge (at minimum: `bluesky_bot_v2.py`, `state_service.py`, `log_sanitizer.py`, `content_service.py`, and any other root modules touched this/prior cycle).
  2. Copy **from root →** `opt/bluesky-bot/` (never the reverse).
  3. If `packaging/_stage/` or build scripts maintain a stage tree, sync or document/update the copy step so stage cannot drift silently.
  4. Prefer a small script or documented one-liner in `ai_docs` / packaging README over ad-hoc manual drift.
- **Acceptance:**
  - MD5/`usedforsecurity`, HTTP helper usage, VAL wiring, creds `sys.exit(1)` present in `opt/bluesky-bot/` copies
  - No secret files copied into stage/opt
  - Brief note in plan report or `ai_docs` that root remains SoT

### CI-001: GitHub Actions unittest job
- **Priority:** High (P1)
- **Complexity:** Simple
- **Dependencies:** None (can start early; finalize after TEST-001 paths exist)
- **Files:** `.github/workflows/ci.yml` (new) or extend existing workflow; avoid breaking `release-deb.yml` / `python-publish.yml`
- **Work:**
  1. Add workflow on `push` + `pull_request` to default branches.
  2. Job: checkout → setup Python → `python -m unittest discover -s tests -v` (and/or `python verify_bot.py` if cheap and hermetic).
  3. No secrets required for unit tests.
- **Acceptance:**
  - Workflow file valid YAML; job name clear (`test` / `unittest`)
  - Discovers `tests/test_*.py`
  - Documented in agents README or short CI note if helpful

### PRA-001: Fix/verify pr-agent workflow + document secret
- **Priority:** High (P1)
- **Complexity:** Simple
- **Dependencies:** None
- **Files:** `.github/workflows/pr-agent.yml`; `agents/README.md` and/or `ai_docs/develop/*` setup note
- **Context:** Current workflow uses `qodo-ai/pr-agent@main` with OpenRouter via `OPENROUTER_API_KEY` mapped to `OPENAI_KEY`. Action pin/`@main` risk; secret cannot be set remotely.
- **Work:**
  1. Verify action org/name/version against current PR-Agent docs; pin to a tag/SHA if feasible (avoid unpinned `@main` if a stable tag exists).
  2. Confirm env var names for OpenRouter bridge still correct.
  3. Add setup note: repo secret `OPENROUTER_API_KEY` must be set in GitHub UI; optional `PR_AGENT_MODEL` var; workflow skips/fails without it — document expected behavior.
  4. Do **not** attempt to write secrets via API.
- **Acceptance:**
  - Workflow reviewed/fixed; docs state required secret and where to set it
  - No credentials in repo

### SMOKE-001: Post-deploy smoke / dry-run check
- **Priority:** High (P1)
- **Complexity:** Moderate
- **Dependencies:** EXIT-001 (exit semantics); optionally REF-001 if importing helpers
- **Files:** `verify_bot.py` extension and/or new `scripts/smoke_check.py` (prefer extending `verify_bot` **or** thin wrapper — avoid third parallel harness)
- **Work:**
  1. Add a **hermetic** smoke mode: import health, config presence checks (without live network if secrets missing), `DRY_RUN` path sanity, fail-fast creds exit code check.
  2. Optional gated live check behind env flag (default off) — do not require network in CI.
  3. Document: `python verify_bot.py` / smoke flag for post-deploy.
- **Acceptance:**
  - Runnable without Bluesky credentials for default hermetic path
  - Exits non-zero on failed checks
  - Documented one-liner for operators

### MED-001: Highest-value MEDIUM fixes (max 2–3)
- **Priority:** Medium (P2)
- **Complexity:** Moderate
- **Dependencies:** None (coordinate with REF-001 if both touch HTTP)
- **Files:** likely `bluesky_rich_posts.py` (`fetch_link_metadata`), `rss_source_manager.py` (`add_candidate`), shared URL helper; optionally cache trim in `bluesky_bot_v2.py`; health surface already partially exists (`health_monitor`)
- **Pick (concrete — do these three unless blocked):**
  1. **SSRF URL validation** for outbound fetches (HTTPS-only, block private/link-local/metadata IPs, size/time limits where applicable) — audit [S5] / ISS-001 MEDIUM
  2. **Confirm session file permissions** remain `0o600` (already done) — no encryption; note deferral in ISS-001
  3. **Easy win:** either (a) bounded eviction/trim for in-memory caches (`content_cache` / engagement sets) if trivial, **or** (b) expose/clarify a lightweight health CLI hook if cache eviction is messy — pick whichever is smaller
- **Explicitly defer:** session encryption at rest; full log-path config redesign; remaining MEDIUM/LOW from audit
- **Acceptance:**
  - SSRF helper + tests (blocked URLs / private IPs rejected)
  - Wired into at least one real fetch path (rich posts and/or RSS candidate add)
  - ISS-001 updated: which MEDIUM rows closed vs still deferred
  - Max 2–3 concrete code fixes (not a MEDIUM sweep)

### REF-001: God-class first slice — HTTP session helper
- **Priority:** Medium (P2)
- **Complexity:** Complex
- **Dependencies:** None; prefer after or with awareness of HTTP-001 patterns already in bot
- **Files:** new module e.g. `http_session.py` (name per project style); thin rewiring in `bluesky_bot_v2.py`; tests update `test_http_session_http001.py`
- **Context:** `_ensure_http_session` / create/close already centralized in the bot (HTTP-001). Next clear extract: move session factory/ensure/close into a dedicated helper module; bot holds reference and delegates. Aligns with audit [A7] direction without full shared-stack rewrite.
- **Work:**
  1. Extract create/ensure/close (and timeouts/connector defaults) to new module.
  2. Bot uses helper; behavior-preserving.
  3. Do **not** extract strategies/RSS/engagement in this cycle.
- **Acceptance:**
  - New module imported by root bot
  - Existing HTTP-001 hermetic tests pass (adapted)
  - LOC moved out of god-class; no behavior change under unittest
  - SYNC-001 will copy new module to `opt/` if deploy tree needs it

### TOOL-001: Dev tooling hygiene
- **Priority:** Medium (P2)
- **Complexity:** Simple
- **Dependencies:** None
- **Files:** `.gitignore`, `agents/README.md`, `agents/security_agent.py` (pip-audit timeout)
- **Work:**
  1. Confirm `reports/` already in `.gitignore` (present ~line 139) — if missing elsewhere, fix; ensure nested report paths covered.
  2. Keep `agents/` first-class: README lists run instructions, CI pointer, secret note (align with PRA-001).
  3. Finish/verify pip-audit timeout handling (non-blocking, documented) — partially done in prior cycle.
- **Acceptance:**
  - `reports/` ignored; no accidental commit of agent reports
  - `agents/README.md` accurate
  - security_agent does not hang CI/local runs indefinitely on pip-audit

### TEST-001: Hermetic tests for this cycle
- **Priority:** High (P1)
- **Complexity:** Moderate
- **Dependencies:** EXIT-001, MED-001, REF-001, SMOKE-001 (as applicable)
- **Files:** `tests/test_*.py`; wire into `verify_bot.py` SSOT pattern where project already does that
- **Work:**
  1. EXIT / SystemExit coverage
  2. SSRF allow/deny cases
  3. HTTP helper module tests (moved/adapted)
  4. Smoke hermetic path
  5. Run full `python -m unittest discover -s tests -v` + `python verify_bot.py`
- **Acceptance:**
  - All new/changed tests green offline
  - No network dependency in default suite

### GIT-001: Clean split commits
- **Priority:** Critical (P0) — user approved commits as part of «всё»
- **Complexity:** Simple
- **Dependencies:** TEST-001 green; SYNC-001 done
- **Agent:** git-helper / orchestrator (conventional commits; **do not** commit secrets `.env`, `session.json`, live creds)
- **Split (adjust only if tree forces clearer grouping):**
  1. **(a)** `fix`/`test`/`docs`: remediation + backlog code (EXIT/MED/REF/SMOKE/SYNC) + tests + `ai_docs` plan/ISS updates
  2. **(b)** `chore(agents)`: agents tooling / security_agent / agents README
  3. **(c)** `chore(ci)` or other: CI workflow, pr-agent, `.gitignore` leftovers not in (a)/(b)
- **Acceptance:**
  - Commits created locally with conventional messages (feat/fix/chore/docs/test/refactor)
  - No secrets staged
  - `git status` clean or only intentional leftovers documented
  - **No push** unless user explicitly asks later

---

## Architecture Decisions

1. **Root SoT + explicit sync** — continue treating repo root modules as source of truth; packaging/`opt` updated only via SYNC-001.
2. **First God-class slice = HTTP helper** — lowest coupling after HTTP-001; content validation already lives in `content_service.py`.
3. **SSRF over encryption** — highest MEDIUM security value this cycle; encryption deferred.
4. **Hermetic CI** — unittest discover only; live Bluesky checks optional/off by default.
5. **Commits split by concern** — easier review/revert; agents tooling separate from runtime bot fixes.

## Implementation Notes

- Prefer small PRs later; this orchestration may produce multiple local commits before any PR.
- When MED-001 and REF-001 both edit `bluesky_bot_v2.py`, serialize: REF extract first, then SSRF wiring — or put URL helper in new `url_safety.py` / extend `content_service` to minimize bot churn.
- Update ISS-001 disposition table when MEDIUM items close.
- Phase 2 backlog below is **out of scope** for this orchestration’s task loop.

---

## Phase 2 (deferred — next orchestration cycle)

| Item | Why deferred |
|------|----------------|
| Session encryption at rest / OS keyring | Large design; 0o600 already in place |
| Remaining audit MEDIUM/LOW (log path config, dual RSS SoT [A6], growth_engine split [A8], etc.) | Exceeds 10-task cap / lower ROI this cycle |
| Further God-class slices (strategies registry, engagement, RSS ingest, orchestrator-only main loop) | REF-001 is first slice only |
| Full shared HTTP stack with Pollinations ([A7] complete) | Partial via REF-001; Pollinations session merge later |
| Setting GitHub `OPENROUTER_API_KEY` remotely | Impossible/unsafe from agent; human UI only |
| `git push` / open PR | User did not request push in this backlog |
| LOW #16–#18 from ISS-001 | Explicitly later |

---

## Subagent Hints (for orchestrator)

| Task | Suggested agent |
|------|-----------------|
| EXIT-001, MED-001, REF-001, SMOKE-001, SYNC-001 | worker |
| CI-001, PRA-001, TOOL-001 | worker |
| TEST-001 | test-writer → test-runner |
| After code tasks | reviewer (light) |
| MED-001 SSRF | security-auditor (proactive skim) |
| REF-001 extract | senior-reviewer optional before/after slice |
| GIT-001 | git-helper conventions; orchestrator commits |

## Success Criteria (cycle)

- [x] Bad creds → exit code 1
- [x] `opt/` (+ stage) synced from root for remediated modules
- [x] CI unittest workflow present
- [x] pr-agent workflow verified + secret documented
- [x] Smoke/hermetic post-deploy check available
- [x] SSRF (+ ≤2 other MEDIUM) landed with tests; encryption still deferred in ISS-001
- [x] HTTP session helper module extracted; god-class smaller
- [x] Tooling hygiene OK
- [x] Hermetic tests green
- [ ] Split conventional commits created locally (GIT-001 — orchestrator)
)
