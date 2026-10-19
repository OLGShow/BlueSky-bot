# Plan: God Object Decomposition — Follow-up (Phase 2+)

**Created:** 2026-10-19  
**Parent orchestration:** orch-2026-10-19-14-33-layout-godobj  
**Parent plan:** `ai_docs/develop/plans/2026-10-19-layout-and-god-object-prep.md`  
**ADR:** `ai_docs/develop/architecture/2026-10-19-layering-and-ports.md`  
**Status:** 🟡 In progress (Phase 2 done; Phase 3 dispatch done; extract + Phases 4–7 remain)  
**Goal:** Complete DIP / OCP decomposition of `AutonomousBlueskyBotV2` beyond Phase 1  
  (Engagement ports + strategy registry skeleton).  
**Priority:** High  
**Mode:** documentation plan for remaining orchestration cycles

**Progress (2026-10-19):**
| Item | Status | Orch / notes |
|------|--------|--------------|
| **Phase 2** — ContentService ports | ✅ Done | `orch-2026-10-19-15-06-godobj-p2` — report: [god-object-phase2-content-strategies-implementation.md](../reports/2026-10-19-god-object-phase2-content-strategies-implementation.md) |
| **Phase 3** — registry register + dispatch | ✅ Done | Same orch — full keys via `build_bound_registry`; `create_scheduled_post` → `weighted_entries` / `resolve` |
| **Phase 3** — strategy-family extract (`STRAT-003`) | ⏸️ Deferred | No `app/strategies/` extract yet; still remaining work |
| **Phases 4–7** | ⬜ Remain | RetryPolicy, quality pipeline, shared HTTP session, further bot slices |

---

## Context (what Phase 1 already did)

| Item | Location | Notes |
|------|----------|-------|
| ADR layering + ports | `ai_docs/develop/architecture/2026-10-19-layering-and-ports.md` | Accepted |
| Engagement ports | `app/engagement_ports.py` | No `bot` in service |
| EngagementService wiring | `app/engagement_service.py` + bot composition root | Phase 1 complete |
| Strategy registry skeleton | `app/post_strategies.py` | Proof register of 1–2 methods; dispatch still `getattr` (superseded by Phase 3 dispatch) |

**Invariant to keep:** services/ports/strategies must not import `bluesky_bot_v2`.  
Bot remains composition root until slices are small enough to drop.

---

## Remaining phases (overview)

| Phase | Name | Est. | Status |
|-------|------|------|--------|
| **2** | ContentService ports + wiring | 3–4h | ✅ Done (`orch-2026-10-19-15-06-godobj-p2`) |
| **3** | Full post strategy extraction | 4–6h | 🟡 Dispatch done; **extract (`STRAT-003`) deferred** |
| **4** | RetryPolicy on outbound I/O | 2–3h | ⬜ Remain |
| **5** | Unified quality pipeline | 3–4h | ⬜ Remain |
| **6** | Shared HTTP `ClientSession` injection | 2h | ⬜ Remain |
| **7** | Further bot slices (state / schedule / learning) | ongoing | ⬜ Remain |

Suggested next orchestration: **Phase 3 extract (STRAT-003+)** and/or **Phase 4**, ≤10 tasks, same verify gate.

---

## Phase 2 — ContentService ports

**Status:** ✅ Completed 2026-10-19 (`orch-2026-10-19-15-06-godobj-p2`)

**Problem:** `ContentService(bot)` still takes the whole bot (same smell Engagement had).

**Done:**
1. Inventory `self.bot.` in `app/content_service.py` → three touchpoints
2. `app/content_ports.py` — `PromptContextPort`, `BackgroundSchedulerPort`, `ContentPorts`
3. `ContentService(ContentPorts)`; bot wires via `_build_content_ports()`
4. Hermetic tests: `tests/test_content_ports_cont004.py`

**Acceptance (met):**
- No `self.bot` in ContentService
- Import graph stays acyclic
- Outbound text / URL behavior unchanged

---

## Phase 3 — Full strategy extraction

**Status:** 🟡 Partial — register + dispatch ✅; family extract ⏸️ deferred

**Problem:** `create_scheduled_post` built strategies via `hasattr` / `getattr`; registry was proof-only.

**Done (dispatch cycle):**
1. Register **all** `post_strategies` config keys into `PostStrategyRegistry` at composition root (`build_bound_registry`)
2. Switch `create_scheduled_post` (and duplicate fallback) to `weighted_entries` / `resolve`
3. Unit tests + verify gate (smoke 2/2; unittest 153 OK, 3 skipped)

**Still remaining:**
3. Move private `_create_*` / media / link-preview helpers into `app/strategies/` modules implementing `PostStrategy` (incremental: one family per PR) — **STRAT-003 deferred**
4. Keep learning / A/B weight updates keyed by **strategy name strings** (stable config keys) — already preserved at dispatch
5. Expand unit tests further as families extract

**Acceptance (dispatch met; extract open):**
- ✅ Runtime dispatch via registry (weights, quality gate regen, duplicates equivalent)
- ✅ `post_strategies.py` remains free of bot imports
- ⬜ New post kinds = register extracted strategy instances (bound methods still interim)

**How to use the registry (current + target extract):**

```python
# composition root (current — bound methods OK)
self.post_strategy_registry = build_bound_registry(self, self.config.get("post_strategies", {}))
# later: register extracted PostStrategy instances instead

# dispatch (current)
entries = self.post_strategy_registry.weighted_entries(
    self.config["post_strategies"], skip_missing=True
)
strategy_fn = self._weighted_choice(entries)
post = await strategy_fn()
```

---

## Phase 4 — RetryPolicy wiring

**Status:** ⬜ Remain

**Problem:** `RetryPolicy` / `classify_error` / `backoff_seconds` exist in `resilience_service` but are not consistently applied to all outbound I/O.

**Actions:**
1. Catalog outbound call sites (ATProto client, OpenRouter/Pollinations, RSS/HTTP, Bluesky uploads)
2. Inject a shared `RetryPolicy` (or per-adapter policies) at composition root
3. Wrap adapters — not the main loop — so services stay free of retry details
4. Tests: fake failing adapter + policy exhaust / success-after-retry

**Acceptance:**
- Documented policy per adapter class
- Main loop does not reimplement ad-hoc retry for those paths
- No silent infinite retries

---

## Phase 5 — Quality pipeline merge

**Status:** ⬜ Remain

**Problem:** Dual quality paths — `QualityGate` (growth_engine) vs `ContentQualityAnalyzer` (ai_improvements) — overlap and confuse regen logic.

**Actions:**
1. Document current responsibilities and call order (audit snippet)
2. Design single pipeline interface (e.g. `check(text, context) -> (ok, reason)`)
3. Migrate `create_scheduled_post` regen loop to one gate; keep analyzer as adapter or merge heuristics
4. Config keys: one namespace for thresholds / max_regen

**Acceptance:**
- One public quality entry point used by scheduled post path
- No divergent “passed gate A / failed gate B” surprises without explicit staging
- Tests for duplicate / low-signal / regen exhaustion

---

## Phase 6 — Shared HTTP session injection

**Status:** ⬜ Remain

**Problem:** `http_session` helpers exist, but not all adapters/services receive the shared `aiohttp.ClientSession` via ports; risk of extra sessions or lifecycle bugs.

**Actions:**
1. Inventory who creates/uses ClientSession
2. Add a narrow `HttpSessionPort` (or pass session into RSS / AI / URL fetch adapters)
3. Ensure single create / recreate / close ownership on the bot (or a small `HttpSessionOwner` adapter)
4. Tests: recreate-after-close; no session use after close

**Acceptance:**
- One owner for session lifecycle
- Adapters do not call `aiohttp.ClientSession()` ad hoc in hot paths
- Packaging / smoke still green

---

## Phase 7 — Further bot slices (backlog)

**Status:** ⬜ Remain

Incremental extractions from `bluesky_bot_v2.py` (order flexible):

- State / persistence façade already partially in `state_service` — finish remaining direct file/memory ops
- Scheduling / main-loop ticks → thin `Scheduler` or cycle runner
- Learning hooks (`bot_learning_module`, strategy weight updates) → application service + ports
- Engagement timeline / smart engagement orchestration (above EngagementService)
- Dry-run reporting aggregation

Each slice: ports → wire → tests → shrink bot LOC. Prefer ≤1 major slice per orchestration.

---

## Verify gate (every follow-up cycle)

```bash
python verify_bot.py --smoke
python -m unittest discover -s tests -v
```

Also re-sync packaging when new `app/*.py` SoT modules are added:

```bash
bash packaging/sync-opt-from-sot.sh
```

---

## Risks

| Risk | Mitigation |
|------|------------|
| Strategy extraction breaks learning name map | Keep config keys stable; map types → names in one place |
| ContentService port inventory incompleteness | Grep `self.bot.` before freezing Protocols (✅ done Phase 2) |
| Retry + quality changes alter engagement rate | Feature-flag or dry-run compare; hermetic tests first |
| Scope creep back into God Object “just one more method” | Enforce OCP: new post kinds → registry only |

---

## References

- Phase 2+ report: `ai_docs/develop/reports/2026-10-19-god-object-phase2-content-strategies-implementation.md`
- Phase 2+ plan: `ai_docs/develop/plans/2026-10-19-god-object-phase2-content-strategies.md`
- ADR-001: `ai_docs/develop/architecture/2026-10-19-layering-and-ports.md`
- Prep plan (Phase 0–1): `ai_docs/develop/plans/2026-10-19-layout-and-god-object-prep.md`
- Audit: `ai_docs/develop/audits/2026-10-19-architecture-and-layout.md`
- Skeleton: `app/post_strategies.py`
