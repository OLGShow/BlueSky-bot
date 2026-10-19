# Plan: Phase 7 Leftovers — Heartbeat, Cache Sync, Smart Engagement

**Created:** 2026-10-19 18:52  
**Orchestration:** `orch-2026-10-19-18-52-p7-hb-eng`  
**Parent / follow-up:** `ai_docs/develop/plans/2026-10-19-god-object-decomposition-followup.md`  
**Prior cycle:** `orch-2026-10-19-18-33-softfail-state` (soft-fail + `ContentPublishState`)  
**ADR:** `ai_docs/develop/architecture/2026-10-19-layering-and-ports.md`  
**Status:** ✅ Completed  
**Goal:** Clear remaining deferred Phase 7 / God Object leftovers: heartbeat file I/O, engagement cache ↔ memory sync, smart-engagement timeline orchestration above `EngagementService`; dry-run reporting aggregation only if budget allows.  
**Priority:** High  
**Total Tasks:** 10  
**Estimated Time:** ~8–12 hours  
**Mode:** docs (plans enabled)

---

## Constraints (hard)

| Rule | Detail |
|------|--------|
| Import graph | New modules must **NOT** import `bluesky_bot_v2` |
| Composition root | Bot remains composition root; thin delegates only |
| Pattern | Ports / helpers in `app/`; wire via callables in `_build_*` |
| Existing | Reuse `state_service`, `engagement_service` / `engagement_ports`, `bot_cycle`, `BotMemory` caches |
| Packaging | New SoT modules in `packaging/sync-opt-from-sot.sh` + opt mirror |
| Verify | `python verify_bot.py --smoke` ; `python -m unittest discover -s tests -v` |
| Git | **No commits** in this orchestration |
| Scope | ≤10 tasks; focused slices |

**Cut order if over budget:**
1. Drop **DRY-001** first (dry-run reporting aggregation)
2. Then drop **ENG-001 / ENG-002** (timeline orchestration) — keep HB + CACHE + PKG + VERIFY
3. Note dropped items back in follow-up plan

---

## Inventory (frozen at plan time)

SoT: `app/bluesky_bot_v2.py` (opt mirror is sync target, not SoT).

### Heartbeat / hang check

| Method / site | ~Lines | Role | Call sites |
|---------------|--------|------|------------|
| `__init__` heartbeat fields | ~664–666 | `last_heartbeat`, `heartbeat_file='bot_heartbeat.txt'` | construction |
| `_update_heartbeat` | ~1042–1051 | Write ISO timestamp + PID + status to file | `BotCycleRunner.tick` via ports |
| `_check_for_hanging` | ~1053–1076 | Read file; hang if age > 900s | **No callers in bot** (dead on bot; external monitor duplicates logic) |
| `app/bot_monitor.py` `check_heartbeat` | ~18–44 | Standalone monitor read of same file | CLI / monitor entry |
| `state_service.SingleInstanceLock.heartbeat` | ~450–453 | **Different** — lock JSON refresh, not `bot_heartbeat.txt` | lock watchdog |

**Target:** shared `HeartbeatMonitor` (or `state_service` helper) owning write + stale check; bot thin delegates; optionally align `bot_monitor` to call helper (no behavior change).

### Engagement cache ↔ memory sync

| Method / site | ~Lines | Role |
|---------------|--------|------|
| Init hydrate from memory | ~472–473+ | `liked_posts` / `reposted_posts` / etc. from `memory.*_cache` |
| `_sync_duplicate_caches_to_memory` | ~737–744 | Cycle path: commented / recent_comments / liked / reposted / followed → memory + `last_update` |
| `shutdown` final persist | ~2528–2541 | **Duplicate** of same field copies before `memory.save()` |
| `_trim_in_memory_caches` | ~1158+ | Size caps; related but stays on bot or shared trim helper if cheap |

**Target:** one `EngagementCacheSync` (or method on memory/state helper) used by cycle + shutdown; bot cycle port stays thin.

### Smart engagement / timeline orchestration

| Method / site | ~Lines | Role |
|---------------|--------|------|
| `smart_engagement` | ~2141–~2500+ | Timeline pages → score → like/repost/comment via `engagement_service`; fills `_trend_timeline_snippets` |
| `BotCyclePorts.smart_engagement` | `bot_cycle.py` | Tick calls bot method |
| `_follow_from_timeline` | ~2915+ | Separate follow path (out of scope unless trivial) |
| Trend radar use of snippets | ~1292 | Reads `_trend_timeline_snippets` |

**Target:** orchestrator module **above** `EngagementService` (fetch timeline, score, thresholds, act); bot keeps composition + thin `async def smart_engagement`.

### Dry-run / daily report (cuttable)

| Method / site | ~Lines | Role |
|---------------|--------|------|
| `DryRunAction` | `growth_engine.py` ~271+ | Log + `save()` |
| `_generate_and_save_daily_report` | ~756–762 | `generate_daily_report` + `save_daily_report` + AB persist + dry-run flush |
| `send_post` dry-run log | ~1371–1372 | Ad-hoc log on publish path |
| `DryRunGate` in engagement ports | already extracted | likes/reposts/follows |

**Target if kept:** thin `ReportingFacade` aggregating daily report + dry-run flush (not re-home every `log()` call site).

---

## Tasks Overview

1. **INV-001** — Inventory freeze + module placement  
2. **HB-001** — HeartbeatMonitor helper (write + stale check)  
3. **HB-002** — Wire bot / bot_cycle / optional bot_monitor  
4. **CACHE-001** — Engagement cache ↔ memory sync consolidation  
5. **ENG-001** — Smart engagement orchestrator (timeline + act)  
6. **ENG-002** — Wire thin `smart_engagement` + cycle ports  
7. **TEST-001** — Hermetic tests (HB + CACHE + ENG)  
8. **DRY-001** — Dry-run / daily report aggregation *(cuttable)*  
9. **PKG-001** — Packaging sync + opt mirror  
10. **VERIFY-001** — Smoke + unittest + follow-up docs  

**Active task count:** **10**. If over budget: drop DRY-001 → 9; then drop ENG-001/ENG-002 → 7 (HB+CACHE+TEST+PKG+VERIFY).

---

## Progress (updated by orchestrator)

- ✅ INV-001: Inventory freeze + placement
- ✅ HB-001: HeartbeatMonitor helper
- ✅ HB-002: Heartbeat wire
- ✅ CACHE-001: Cache sync consolidation
- ✅ ENG-001: Smart engagement orchestrator
- ✅ ENG-002: Orchestrator wire
- ✅ TEST-001: Hermetic tests
- ✅ DRY-001: Dry-run reporting aggregation
- ✅ PKG-001: Packaging sync
- ✅ VERIFY-001: Verify gate + docs (smoke 2/2; 294 OK / 3 skipped)

---

## Dependencies Graph

```text
INV-001 → HB-001 → HB-002 ─┐
INV-001 → CACHE-001 ───────┼→ TEST-001 → [DRY-001?] → PKG-001 → VERIFY-001
INV-001 → ENG-001 → ENG-002 ┘
```

**Parallel after INV-001:** `HB-001` ‖ `CACHE-001` ‖ `ENG-001` (ENG wire after extract).  
**Serial gate:** `TEST-001` after HB-002 + CACHE-001 + ENG-002 (or after kept slices if ENG cut).

---

## Architecture Decisions

1. **Heartbeat:** Prefer new small helper in `app/state_service.py` **or** `app/heartbeat_monitor.py` if `state_service` is already large. Own path, update(), is_stale(threshold_seconds=900). Do **not** conflate with `SingleInstanceLock.heartbeat`.
2. **Cache sync:** Pure/helper function or class taking memory + cache sets/lists; one call from cycle + shutdown. Keep hydrate-on-init on bot (or move later).
3. **Smart engagement:** New module e.g. `app/smart_engagement.py` with ports for timeline fetch (`get_timeline` / `_atproto_execute`), relevance scoring, config thresholds, `EngagementService` actions, trend-snippet sink. **Must not** import bot.
4. **Dry-run:** Only if time left — move `_generate_and_save_daily_report` body behind a façade next to `growth_engine` helpers; leave `DryRunGate` as-is.
5. **Bot remains composition root** until methods shrink to delegates.

---

## Task Details

### INV-001: Inventory freeze + module placement
- **Priority:** Critical  
- **Complexity:** Simple  
- **Time:** ~30–45m  
- **Dependencies:** None  
- **Agent:** worker  
- **Files:** this plan (confirm), `app/state_service.py`, `app/bot_monitor.py`, `app/engagement_service.py`, `app/bot_cycle.py`

**Work:**
1. Confirm inventory tables vs current SoT line ranges.
2. Lock module names: HeartbeatMonitor location; cache sync helper name; smart engagement module path.
3. Confirm cut order with remaining budget (DRY then ENG).

**Acceptance:**
- [ ] Placement decisions written in Architecture Decisions (no TBD)
- [ ] No scope creep into follow strategy / content strategies

---

### HB-001: HeartbeatMonitor helper
- **Priority:** Critical  
- **Complexity:** Simple  
- **Time:** ~1–1.5h  
- **Dependencies:** INV-001  
- **Agent:** worker  
- **Files:** `app/state_service.py` and/or `app/heartbeat_monitor.py` (new)

**Work:**
1. Implement write (ISO + PID + status) and stale/hang check (default 900s).
2. No import of `bluesky_bot_v2`.
3. Preserve file format consumed by `bot_monitor.check_heartbeat`.

**Acceptance:**
- [ ] Helper unit-testable with temp path
- [ ] Behavior parity with current `_update_heartbeat` / `_check_for_hanging`

---

### HB-002: Wire heartbeat into bot (+ optional monitor)
- **Priority:** Critical  
- **Complexity:** Simple  
- **Time:** ~45m–1h  
- **Dependencies:** HB-001  
- **Agent:** worker  
- **Files:** `app/bluesky_bot_v2.py`, optionally `app/bot_monitor.py`, `app/bot_cycle.py` (ports unchanged if signatures stable)

**Work:**
1. Bot: thin `_update_heartbeat` / `_check_for_hanging` delegates; init holds helper or path.
2. Prefer `bot_monitor` to call shared helper (DRY) without changing CLI UX.
3. Keep cycle wiring: ports still call bot update method.

**Acceptance:**
- [ ] No raw open/write of heartbeat file left in bot body (except via helper)
- [ ] Cycle still updates heartbeat each tick

---

### CACHE-001: Engagement cache ↔ memory sync consolidation
- **Priority:** High  
- **Complexity:** Moderate  
- **Time:** ~1–2h  
- **Dependencies:** INV-001  
- **Agent:** worker  
- **Files:** new helper under `app/` (e.g. `engagement_cache_sync.py` or method beside memory in `state_service`), `app/bluesky_bot_v2.py`

**Work:**
1. Extract field copy logic from `_sync_duplicate_caches_to_memory` + `shutdown` into one helper.
2. Wire cycle + shutdown to same helper; keep `last_update` semantics.
3. Do not change trim/hydrate behavior unless needed for single source of truth.

**Acceptance:**
- [ ] One implementation of cache→memory field mapping
- [ ] Cycle + shutdown both use it
- [ ] No bot↔service circular imports

---

### ENG-001: Smart engagement orchestrator
- **Priority:** High  
- **Complexity:** Complex  
- **Time:** ~3–4h  
- **Dependencies:** INV-001  
- **Agent:** worker  
- **Files:** `app/smart_engagement.py` (new) + narrow ports in-module or `engagement_ports` extension

**Work:**
1. Move timeline paging, scoring loop, threshold/quantile logic, like/repost/comment decisions from `smart_engagement`.
2. Inject ports: timeline client, relevance scorer, engagement service (or like/repost/comment callables), config view, trend-snippet sink, interaction caps.
3. Preserve observable behavior (thresholds, max_reposts/comments, dry-run via existing engagement ports).

**Acceptance:**
- [ ] Module does not import `bluesky_bot_v2`
- [ ] Uses `EngagementService` (or same ports) for mutations
- [ ] `_trend_timeline_snippets` still populated for Trend Radar

---

### ENG-002: Wire thin smart_engagement
- **Priority:** High  
- **Complexity:** Simple  
- **Time:** ~45m–1h  
- **Dependencies:** ENG-001  
- **Agent:** worker  
- **Files:** `app/bluesky_bot_v2.py`, `app/bot_cycle.py` (if port shape changes)

**Work:**
1. Composition-root build of orchestrator ports.
2. `smart_engagement` becomes thin `await orchestrator.run()`.
3. Cycle continues to call bot method / port.

**Acceptance:**
- [ ] Bot method body is thin delegate
- [ ] Tick path unchanged from outside

---

### TEST-001: Hermetic tests
- **Priority:** High  
- **Complexity:** Moderate  
- **Time:** ~1.5–2h  
- **Dependencies:** HB-002, CACHE-001, ENG-002 (or subset if ENG cut)  
- **Agent:** test-writer  
- **Files:** `tests/test_heartbeat_*.py`, `tests/test_engagement_cache_*.py`, `tests/test_smart_engagement_*.py`

**Work:**
1. Heartbeat: write + stale true/false with temp files.
2. Cache sync: mapping + last_update with fake memory.
3. Smart engagement: fake timeline + engagement service; assert like/repost gates without network.

**Acceptance:**
- [ ] New tests pass under `unittest discover`
- [ ] No live network / ATProto

---

### DRY-001: Dry-run / daily report aggregation *(cuttable)*
- **Priority:** Low  
- **Complexity:** Simple  
- **Time:** ~1h  
- **Dependencies:** TEST-001 (or parallel after CACHE if ENG cut)  
- **Agent:** worker  
- **Files:** `app/growth_engine.py` and/or small `app/reporting.py`, `app/bluesky_bot_v2.py`

**Work:**
1. Extract `_generate_and_save_daily_report` into façade (daily report + AB persist + dry-run save).
2. Do **not** chase every `dry_run_log.log` call site in this slice.

**Acceptance:**
- [ ] Bot method is thin delegate
- [ ] Dry-run flush still runs when `DRY_RUN` enabled

**Cut note:** If dropped, document in VERIFY-001 / follow-up as still deferred.

---

### PKG-001: Packaging sync + opt mirror
- **Priority:** Critical  
- **Complexity:** Simple  
- **Time:** ~20–30m  
- **Dependencies:** TEST-001 (+ DRY-001 if done)  
- **Agent:** worker  
- **Files:** `packaging/sync-opt-from-sot.sh`, `opt/bluesky-bot/*`

**Work:**
1. Add any new `app/*.py` to sync list if not globbed.
2. Run sync so opt mirror matches SoT.

**Acceptance:**
- [ ] New modules present under `opt/bluesky-bot/`
- [ ] No hand-edited SoT under `opt/`

---

### VERIFY-001: Smoke + unittest + follow-up docs
- **Priority:** Critical  
- **Complexity:** Simple  
- **Time:** ~30–45m  
- **Dependencies:** PKG-001  
- **Agent:** test-runner (+ documenter notes)  
- **Files:** follow-up plan status, this plan Progress section

**Work:**
1. Run `python verify_bot.py --smoke`
2. Run `python -m unittest discover -s tests -v`
3. Update `2026-10-19-god-object-decomposition-followup.md` Phase 7 deferred list (mark done / still deferred).
4. No git commit.

**Acceptance:**
- [ ] Smoke green
- [ ] Unittest green (skips OK if pre-existing)
- [ ] Follow-up plan reflects remaining backlog accurately

---

## Risks

| Risk | Mitigation |
|------|------------|
| Smart engagement extract breaks engagement rates | Hermetic tests for thresholds; no threshold tuning in this orch |
| Heartbeat format drift breaks external monitor | Keep exact line format; share helper with `bot_monitor` |
| Cache sync miss on shutdown | Single helper; grep for `*_cache =` assignments |
| Scope creep into dry-run log sites | DRY-001 only aggregates daily flush; cut if late |

---

## References

- Follow-up: `ai_docs/develop/plans/2026-10-19-god-object-decomposition-followup.md`
- Prior plan: `ai_docs/develop/plans/2026-10-19-softfail-state-facade.md`
- ADR-001: `ai_docs/develop/architecture/2026-10-19-layering-and-ports.md`
- Existing: `app/state_service.py`, `app/engagement_service.py`, `app/bot_cycle.py`, `app/bot_monitor.py`, `app/growth_engine.py`
