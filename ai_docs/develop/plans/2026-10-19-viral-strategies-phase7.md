# Plan: Viral/Trending Strategies + Phase 7 Slices

**Created:** 2026-10-19 17:51  
**Orchestration:** `orch-2026-10-19-17-51-viral-p7`  
**Parent / follow-up:** `ai_docs/develop/plans/2026-10-19-god-object-decomposition-followup.md`  
**Prior cycle:** `orch-2026-10-19-17-34-strat-families` (dynamic/theme/poll/insight + HTTP/Retry; viral deferred)  
**ADR:** `ai_docs/develop/architecture/2026-10-19-layering-and-ports.md`  
**Status:** ✅ Completed  
**Goal:** Extract remaining viral/trending post strategies into `app/strategies/`; then cut **two** Phase 7 bot slices (learning weight updates + thin cycle runner). Soft-fail helpers and remaining state façade → follow-up.  
**Priority:** High  
**Total Tasks:** 8  
**Estimated Time:** ~10–14 hours  
**Mode:** docs (plans enabled)

---

## Constraints (hard)

| Rule | Detail |
|------|--------|
| Import graph | `strategies/` (and new Phase 7 services) must **NOT** import `bluesky_bot_v2` |
| Config / learning keys | Stable: `_create_viral_hot_take`, `_create_trending_commentary` (and all existing `post_strategies` keys) |
| Pattern | `QualityNewsStrategy` / `ThemePostHelper` / hybrid registry `overwrite=True` |
| Packaging | `strategies/` (and any new SoT modules) in `packaging/sync-opt-from-sot.sh` + opt mirror |
| Verify | `python verify_bot.py --smoke` ; `python -m unittest discover -s tests -v` |
| Git | **No commits** in this orchestration |
| Scope | ≤10 tasks; soft-fail + excess Phase 7 **deferred** |

**Cut order if over budget:** drop CYCLE-001 first → keep STRAT-009..011 + LEARN-001 + PKG + VERIFY.

---

## Inventory (remaining after news/dynamic/theme/poll/insight)

| Family | Bot methods (SoT: `app/bluesky_bot_v2.py`) | Pattern | This cycle |
|--------|---------------------------------------------|---------|------------|
| Viral / trending | `_create_viral_hot_take` (~1715), `_create_trending_commentary` (~1763) | topic/theme list + `generate_structured_post_content` + `ImagePostHelper` / `_create_post_with_image_generation`; viral uses `engagement_optimizer.generate_viral_post_prompts()` | **STRAT-009…011** |
| Soft-fail helpers | `_create_motivational_moment_post`, `_create_emergency_unique_post`, `_create_fallback_post_for_duplicate` | duplicate / emergency paths (already partially ported as `FallbackPostPort`) | **Deferred** |
| Phase 7 — learning | `_update_strategy_weights_from_memory` (~2940); callers in delayed performance check | mutates `config['post_strategies']` from `memory.topic_outcomes` | **LEARN-001** |
| Phase 7 — cycle | `run_bot_cycle` (~2579) while-loop: engagement → post window → learn cadence → memory save | orchestration tick | **CYCLE-001** |
| Phase 7 — state | remaining direct memory/file ops beyond `state_service` | façade finish | **Deferred** |

Default learning/config keys for viral family must stay exactly `_create_viral_hot_take` / `_create_trending_commentary` (see `ai_improvements` defaults and `post_strategies` config).

---

## Tasks Overview

1. **STRAT-009** — Inventory deps + viral ports surface  
2. **STRAT-010** — Extract `ViralHotTakeStrategy` + `TrendingCommentaryStrategy`  
3. **STRAT-011** — Hybrid registry wire + thin bot delegates  
4. **TEST-001** — Hermetic tests for viral/trending (+ import-acyclic)  
5. **LEARN-001** — Phase 7: strategy weight-update service + ports  
6. **CYCLE-001** — Phase 7: thin bot-cycle / tick runner  
7. **PKG-001** — Packaging sync + opt mirror  
8. **VERIFY-001** — Smoke + unittest + follow-up plan update  

---

## Progress (updated by orchestrator)

- ✅ STRAT-009: Inventory + viral ports
- ✅ STRAT-010: Viral/trending extract
- ✅ STRAT-011: Registry wire + thin delegates
- ✅ TEST-001: Viral strategy tests
- ✅ LEARN-001: Learning weight-update service
- ✅ CYCLE-001: Cycle / tick runner
- ✅ PKG-001: Packaging sync
- ✅ VERIFY-001: Verify gate + docs (smoke 2/2; 264 OK / 3 skipped)

---

## Dependencies Graph

```text
STRAT-009 → STRAT-010 → STRAT-011 → TEST-001 ─┐
LEARN-001 (after STRAT-011 keys stable) ──────┼→ PKG-001 → VERIFY-001
CYCLE-001 (independent of strategies) ────────┘

Parallel after STRAT-011:
  TEST-001 ‖ LEARN-001 ‖ CYCLE-001
```

Deferred (note in VERIFY-001 follow-up only): soft-fail strategy extract; remaining state façade; engagement timeline orchestration; dry-run reporting aggregation.

---

## Task Details

### STRAT-009: Inventory deps + viral ports surface
- **Priority:** Critical  
- **Complexity:** Simple  
- **Time:** ~45m  
- **Dependencies:** None  
- **Agent:** worker  
- **Files:** `app/strategies/ports.py` (extend docs/Protocols if needed), plan inventory freeze

**Work:**
1. Grep/confirm all call sites and deps of `_create_viral_hot_take` and `_create_trending_commentary`:
   - `engagement_optimizer.generate_viral_post_prompts`
   - `generate_structured_post_content` / image helper path
   - content types `'viral_hot_take'` / `'trending_commentary'`
2. Map bot attrs → ports (prefer reuse `ImagePostPorts` / structured-content port from STRAT-004; add thin Protocol only if viral prompts need a new port).
3. Document mapping table in `ports.py` (same style as news/theme); mark soft-fail as still deferred.

**Acceptance:**
- [ ] Written mapping: bot method → port/helper for both viral kinds
- [ ] No new `bluesky_bot_v2` imports in `strategies/`
- [ ] Soft-fail explicitly out of scope for this orch

---

### STRAT-010: Extract viral/trending strategies
- **Priority:** Critical  
- **Complexity:** Moderate  
- **Time:** ~2.5h  
- **Dependencies:** STRAT-009  
- **Agent:** worker → test-writer (tests in TEST-001)  
- **Files:** `app/strategies/viral_posts.py` (new), `app/strategies/__init__.py`, thin stubs later in STRAT-011

**Work:**
1. Add `VIRAL_HOT_TAKE_STRATEGY_NAME = "_create_viral_hot_take"` and `TRENDING_COMMENTARY_STRATEGY_NAME = "_create_trending_commentary"`.
2. Implement `ViralHotTakeStrategy` and `TrendingCommentaryStrategy` with async `create()` via `ImagePostHelper` (parity with current prompts/fallbacks/topic lists).
3. Inject ports at composition root only — strategies must not import bot.

**Acceptance:**
- [ ] Module imports without `bluesky_bot_v2`
- [ ] Behavior parity: topic pick, AI JSON path, fallback text, image helper content_type keys unchanged
- [ ] Stable `STRATEGY_NAME` constants match config/learning keys

---

### STRAT-011: Hybrid registry wire + thin bot delegates
- **Priority:** Critical  
- **Complexity:** Simple  
- **Time:** ~1h  
- **Dependencies:** STRAT-010  
- **Agent:** worker  
- **Files:** `app/bluesky_bot_v2.py` (`_build_post_strategy_registry`, composition-root build, thin `_create_*` delegates), `app/strategies/__init__.py`

**Work:**
1. Build strategy instances next to other extracted families (reuse `ThemePostHelper` / image ports wiring).
2. Extend `extracted_overwrites` with viral + trending (`overwrite=True`).
3. Replace method bodies with `return await self.*_strategy.create()`.

**Acceptance:**
- [ ] Config keys resolve to extracted instances (not bound bot methods) when present in `post_strategies`
- [ ] Learning / A/B weight key strings unchanged
- [ ] Hybrid registry log still reports registered counts

---

### TEST-001: Hermetic tests for viral/trending
- **Priority:** High  
- **Complexity:** Moderate  
- **Time:** ~1.5h  
- **Dependencies:** STRAT-011  
- **Agent:** test-writer → test-runner  
- **Files:** `tests/test_viral_strategies_strat010.py` (name flexible)

**Work:**
1. Fake ports: happy path + empty structured → fallback + image miss → text-only.
2. Assert strategy name constants == config keys.
3. Import-acyclic check: `strategies.viral_posts` must not pull `bluesky_bot_v2`.

**Acceptance:**
- [ ] Unittests green for both strategies
- [ ] No network / live ATProto in tests
- [ ] Acyclic import assertion present

---

### LEARN-001: Phase 7 — strategy weight-update service
- **Priority:** High  
- **Complexity:** Moderate  
- **Time:** ~2h  
- **Dependencies:** STRAT-011 (keys must stay stable; can start after STRAT-010 if careful)  
- **Agent:** worker → test-writer  
- **Files:** e.g. `app/strategy_learning.py` or extend existing learning module; thin call from bot; **no** bot import in service

**Work:**
1. Extract `_update_strategy_weights_from_memory` logic into a pure/application function or small service:
   - inputs: `topic_outcomes`, current `post_strategies` weights
   - outputs: updated weights dict (or mutate via narrow port)
   - preserve ±10% / clamp `[0.05, 0.50]` / fuzzy topic match behavior
2. Bot keeps composition-root call site in delayed performance check; optional port for config persist if needed.
3. Hermetic unit tests: above-avg → weight up; below → down; clamp bounds; empty outcomes no-op.

**Acceptance:**
- [ ] Service/module does not import `bluesky_bot_v2`
- [ ] Weight keys remain exact `post_strategies` strings (incl. viral keys)
- [ ] Bot method is thin delegate or direct call to service
- [ ] Hermetic tests cover clamp + empty + delta directions

---

### CYCLE-001: Phase 7 — thin bot-cycle / tick runner
- **Priority:** Medium (drop first if over budget)  
- **Complexity:** Complex  
- **Time:** ~2.5h  
- **Dependencies:** None (parallel with LEARN after STRAT-011 preferred for verify order)  
- **Agent:** worker → test-writer  
- **Files:** e.g. `app/bot_cycle.py` + ports; `app/bluesky_bot_v2.py` `run_bot_cycle` shrinks to wire + loop

**Work:**
1. Define narrow ports / callables for one tick: heartbeat, engagement gate, follow cadence, posting window + `create_scheduled_post`, learn cadence, memory save/trim, cleanup hooks (keep implementations on bot as adapters).
2. Extract **one-tick** orchestration (not full while-loop I/O) into `BotCycleRunner.tick(...)` or equivalent — bot retains `while True` + sleep/error handling unless trivially movable.
3. Do **not** move authenticate, ATProto client, or strategy bodies.
4. Hermetic test: fake ports assert call order for a typical tick (engagement on → post when window → skip learn when cadence not met).

**Acceptance:**
- [ ] Cycle module does not import `bluesky_bot_v2`
- [ ] Observable tick order preserved for default config
- [ ] Soft-fail / emergency paths inside post creation untouched
- [ ] Unit test with fakes for tick sequencing

---

### PKG-001: Packaging sync + opt mirror
- **Priority:** High  
- **Complexity:** Simple  
- **Time:** ~30m  
- **Dependencies:** STRAT-010, LEARN-001, CYCLE-001 (any new `app/*.py` / `strategies/`)  
- **Agent:** worker  
- **Files:** `packaging/sync-opt-from-sot.sh`, `packaging/build-deb.sh` (if listed), run sync script

**Work:**
1. Ensure new modules under `app/strategies/` and any new Phase 7 SoT files are included in sync.
2. Run packaging sync / opt mirror so deploy tree matches SoT.

**Acceptance:**
- [ ] Sync script lists/copies new paths
- [ ] `opt/bluesky-bot/` mirror contains new modules (or documented equivalent)
- [ ] No hand-edited SoT under `opt/`

---

### VERIFY-001: Smoke + unittest + follow-up docs
- **Priority:** Critical  
- **Complexity:** Simple  
- **Time:** ~45m  
- **Dependencies:** PKG-001, TEST-001, LEARN-001, CYCLE-001  
- **Agent:** test-runner → documenter (notes only)  
- **Files:** follow-up plan status; optional short report via documenter later

**Work:**
1. Run:
   ```bash
   python verify_bot.py --smoke
   python -m unittest discover -s tests -v
   ```
2. Update `ai_docs/develop/plans/2026-10-19-god-object-decomposition-followup.md`:
   - Phase 3 viral extract ✅ (if done)
   - Phase 7: LEARN + CYCLE done; soft-fail + state façade still deferred
3. **No git commit.**

**Acceptance:**
- [ ] Smoke passes
- [ ] Unittest suite green (allow existing skips only)
- [ ] Follow-up plan reflects remaining backlog
- [ ] No commit created

---

## Architecture Decisions

- Reuse `ImagePostHelper` / STRAT-004 ports; avoid a parallel image path for viral.
- Hybrid registry overwrite keeps learning/A/B config keys stable (OCP without renaming).
- Phase 7 picks **learning weights** + **cycle tick** only; soft-fail strategies and state façade wait for next orch.
- Bot remains composition root (ADR-001).

## Implementation Notes

- Viral hot-take needs a port or callable for `generate_viral_post_prompts` (static method today on optimizer — inject or call via narrow Protocol).
- Trending commentary does not call live `BlueSkyTrendingTracker` yet (static theme list) — do not expand scope to live trending API.
- CYCLE-001: prefer extracting `tick` over relocating the entire infinite loop + sleep/backoff in one step.
- If CYCLE-001 slips schedule: mark deferred in VERIFY-001 and keep LEARN-001.

## Risks

| Risk | Mitigation |
|------|------------|
| Weight updater breaks viral key matching | Freeze key strings; tests assert viral keys in clamp path |
| Cycle extract changes cadence off-by-one | Fake-port order test; keep counters on bot |
| Soft-fail still on bot confuses “all strategies extracted” | Explicit deferral in follow-up + ports docstring |
| Scope creep into state façade | Cut order: drop CYCLE before expanding state |

## References

- Follow-up: `ai_docs/develop/plans/2026-10-19-god-object-decomposition-followup.md`
- Prior orch plan: `ai_docs/develop/plans/2026-10-19-strat-families-http-retry.md`
- ADR-001: `ai_docs/develop/architecture/2026-10-19-layering-and-ports.md`
- Pattern: `app/strategies/theme_posts.py`, `app/strategies/quality_news.py`, `app/bluesky_bot_v2.py` `_build_post_strategy_registry`
