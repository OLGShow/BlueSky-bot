# Report: God Object Phase 2+ — ContentService Ports + Strategy Registry Wiring

**Date:** 2026-10-19  
**Orchestration:** orch-2026-10-19-15-06-godobj-p2  
**Status:** ✅ Completed (1 task deferred)  
**Plan:** [2026-10-19-god-object-phase2-content-strategies.md](../plans/2026-10-19-god-object-phase2-content-strategies.md)  
**Follow-up:** [2026-10-19-god-object-decomposition-followup.md](../plans/2026-10-19-god-object-decomposition-followup.md)  
**ADR:** [2026-10-19-layering-and-ports.md](../architecture/2026-10-19-layering-and-ports.md)  
**Parent:** orch-2026-10-19-14-33-layout-godobj

## Summary

Completed Phase 2 DIP for `ContentService` (narrow ports, no `bot`) and Phase 3 registry wiring: full `post_strategies` registration at the composition root and `create_scheduled_post` dispatch via `PostStrategyRegistry`. Optional strategy-family extract (`STRAT-003`) deferred. Verify gate: **smoke 2/2**; **unittest 153 OK (3 skipped)**.

## What Was Built

### ContentService ports (CONT-001…004)

- **CONT-001:** Inventory — three bot touchpoints → `PromptContextPort` + `BackgroundSchedulerPort`.
- **CONT-002:** New `app/content_ports.py` — Protocols + `LivePromptContext` / `LiveBackgroundScheduler` + `ContentPorts` aggregate (stdlib/typing only).
- **CONT-003:** `ContentService(ContentPorts)`; composition root `_build_content_ports()`; no `self.bot` in content service.
- **CONT-004:** Hermetic tests in `tests/test_content_ports_cont004.py` (ports / no-bot AST / prompt / schedule).

### Packaging (PKG-001)

- `content_ports.py` added to both PYFILES lists; `post_strategies.py` already listed.
- `packaging/sync-opt-from-sot.sh` — 23 files, no WARN.

### Strategy registry wiring (STRAT-001…002; STRAT-003 deferred)

- **STRAT-001:** All `bot_config` `post_strategies` keys (6) registered via `build_bound_registry`.
- **STRAT-002:** `create_scheduled_post` uses `weighted_entries(skip_missing=True)`; duplicate fallback uses `resolve` + getattr for non-config names; weights / quality / duplicates / learning keys preserved.
- **STRAT-003:** ⏸️ Deferred — no `app/strategies/` family extract this cycle.

### Verification (TEST-001)

- Smoke: `python verify_bot.py --smoke` — **2/2 passed**
- Unittest: `python -m unittest discover -s tests -q` — **Ran 153, OK (skipped=3)**
- Registry coverage: `tests/test_post_strategies_strat.py`

## Completed Tasks

1. ✅ **CONT-001:** Inventory `self.bot` in ContentService  
   - Three touchpoints → PromptContextPort + BackgroundSchedulerPort

2. ✅ **CONT-002:** Define `content_ports.py` Protocols  
   - Files: `app/content_ports.py`

3. ✅ **CONT-003:** Refactor ContentService + wire composition root  
   - Files: `app/content_service.py`, `app/bluesky_bot_v2.py`, `app/content_ports.py`

4. ✅ **CONT-004:** Hermetic ContentService port tests  
   - Files: `tests/test_content_ports_cont004.py`

5. ✅ **PKG-001:** Packaging PYFILES + opt mirror sync  
   - Files: `packaging/build-deb.sh`, `packaging/sync-opt-from-sot.sh`, opt mirrors

6. ✅ **STRAT-001:** Register all `post_strategies` keys at composition root  
   - Files: `app/bluesky_bot_v2.py`, `app/post_strategies.py`

7. ✅ **STRAT-002:** Switch `create_scheduled_post` to registry dispatch  
   - Files: `app/bluesky_bot_v2.py`, `app/post_strategies.py` (docstring)

8. ⏸️ **STRAT-003:** Optional extract one strategy family to `app/strategies/`  
   - Deferred — remaining Phase 3 extraction stays in follow-up plan

9. ✅ **TEST-001:** Registry tests + smoke/unittest verify gate  
   - Smoke 2/2; unittest 153 OK, 3 skipped

## Technical Decisions

- **DIP mirror Engagement:** ContentService injects narrow Protocols, not `bot`.
- **Port split:** prompt context (AB suffix, quality-regen) vs background scheduler (spawn + delayed performance check).
- **Phase 3 interim:** bound methods via `build_bound_registry` OK per ADR; class extract incremental (STRAT-003 deferred).
- **Dispatch semantics:** `skip_missing=True` + empty-list error log matches prior `hasattr` skip behavior.
- **Stable strategy names:** config keys remain learning / A/B weight keys.

## Metrics

| Metric | Value |
|--------|-------|
| Tasks | **8/9** completed, **1** deferred (`STRAT-003`) |
| Smoke | **2/2** passed |
| Unittest | **153** ran, **3** skipped, **0** failed |
| Parent orch | orch-2026-10-19-14-33-layout-godobj |

## Known Issues / Deferred

- **STRAT-003** — strategy-family extract to `app/strategies/` still deferred (follow-up Phase 3 remainder).
- **Phases 4–7** remain: RetryPolicy, quality pipeline merge, shared HTTP session, further bot slices — see follow-up plan.

## Related Documentation

- Plan: [2026-10-19-god-object-phase2-content-strategies.md](../plans/2026-10-19-god-object-phase2-content-strategies.md)
- Follow-up: [2026-10-19-god-object-decomposition-followup.md](../plans/2026-10-19-god-object-decomposition-followup.md)
- ADR: [2026-10-19-layering-and-ports.md](../architecture/2026-10-19-layering-and-ports.md)
- Parent report: [2026-10-19-layout-and-god-object-prep-implementation.md](./2026-10-19-layout-and-god-object-prep-implementation.md)

## Next Steps

1. Phase 3 remainder: extract strategy families to `app/strategies/` (STRAT-003+)
2. Phase 4: RetryPolicy on outbound I/O
3. Phase 5: Unified quality pipeline
4. Phase 6: Shared HTTP `ClientSession` injection
5. Phase 7: Further bot slices (state / schedule / learning)
