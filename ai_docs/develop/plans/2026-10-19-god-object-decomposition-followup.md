# Plan: God Object Decomposition — Follow-up (Phase 2+)

**Created:** 2026-10-19  
**Parent orchestration:** orch-2026-10-19-14-33-layout-godobj  
**Parent plan:** `ai_docs/develop/plans/2026-10-19-layout-and-god-object-prep.md`  
**ADR:** `ai_docs/develop/architecture/2026-10-19-layering-and-ports.md`  
**Status:** 🟡 In progress (Phases 2–6 advanced; Phase 3 viral/fallback leftovers + Phase 7 deferred)  
**Goal:** Complete DIP / OCP decomposition of `AutonomousBlueskyBotV2` beyond Phase 1  
  (Engagement ports + strategy registry skeleton).  
**Priority:** High  
**Mode:** documentation plan for remaining orchestration cycles

**Progress (2026-10-19):**
| Item | Status | Orch / notes |
|------|--------|--------------|
| **Phase 2** — ContentService ports | ✅ Done | `orch-2026-10-19-15-06-godobj-p2` — report: [god-object-phase2-content-strategies-implementation.md](../reports/2026-10-19-god-object-phase2-content-strategies-implementation.md) |
| **Phase 3** — registry register + dispatch | ✅ Done | Same orch — full keys via `build_bound_registry`; `create_scheduled_post` → `weighted_entries` / `resolve` |
| **Phase 3** — news-family extract (`STRAT-003`) | ✅ Done | `orch-2026-10-19-17-06-strat003-io` — `app/strategies/quality_news.py` + hybrid registry |
| **Phase 3** — most strategy families | ✅ Done (viral deferred) | `orch-2026-10-19-17-34-strat-families` — dynamic / theme / poll / insight+prediction extracted; **viral + soft-fail helpers deferred** |
| **Phase 4** — RetryPolicy | ✅ Done (AI+RSS+ATProto/media) | Prior orch AI/RSS; `orch-2026-10-19-17-34-strat-families` — ATProto + media upload via RetryPolicy |
| **Phase 5** — quality pipeline | ✅ On scheduled post | `orch-2026-10-19-17-06-strat003-io` — `QualityPipeline` / `regenerate_until_quality` on `create_scheduled_post` |
| **Phase 6** — shared HTTP | ✅ Done | AI adapters + formatter / rich_posts shared session (`HTTP-002`) |
| **Phase 7** | ⬜ Deferred | Further bot slices (own ≤10-task cycle) |

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
| **3** | Full post strategy extraction | 4–6h | ✅ Most families done (`orch-2026-10-19-17-34-strat-families`); **viral / soft-fail leftovers deferred** |
| **4** | RetryPolicy on outbound I/O | 2–3h | ✅ Done — AI+RSS + ATProto/media (`orch-2026-10-19-17-34-strat-families`) |
| **5** | Unified quality pipeline | 3–4h | ✅ Scheduled-post path (`orch-2026-10-19-17-06-strat003-io`) |
| **6** | Shared HTTP `ClientSession` injection | 2h | ✅ Done — AI + formatter/rich_posts (`HTTP-002`) |
| **7** | Further bot slices (state / schedule / learning) | ongoing | ⬜ **Deferred** — own cycle |

Suggested next orchestration: **viral / soft-fail strategy leftovers** and/or **Phase 7** (scheduler / learning / state), ≤10 tasks, same verify gate.

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

**Status:** ✅ Most families extracted (`orch-2026-10-19-17-34-strat-families`); **viral + soft-fail helpers deferred**

**Problem:** `create_scheduled_post` built strategies via `hasattr` / `getattr`; registry was proof-only.

**Done (dispatch cycle):**
1. Register **all** `post_strategies` config keys into `PostStrategyRegistry` at composition root (`build_bound_registry`)
2. Switch `create_scheduled_post` (and duplicate fallback) to `weighted_entries` / `resolve`
3. Unit tests + verify gate (smoke 2/2; unittest 153 OK, 3 skipped)

**Done (news extract — `orch-2026-10-19-17-06-strat003-io`):**
- `app/strategies/` package + `QualityNewsStrategy` (`quality_news.py`)
- Hybrid registry overwrites `_create_quality_news_post` with extracted strategy; learning key stable
- Packaging sync for `strategies/`

**Done (`orch-2026-10-19-17-34-strat-families` — most families):**
- Shared `ImagePostHelper` / theme ports (STRAT-004)
- Dynamic: opinion + tip + discussion (`dynamic_posts.py`, STRAT-005)
- Theme: ai_insight + list (`theme_posts.py`, STRAT-006)
- Poll: quality poll (`poll_post.py`, STRAT-007)
- Insight + prediction (`insight_posts.py`, STRAT-008)
- Learning / A/B weight keys remain stable config strings
- VERIFY-001: smoke 2/2; unittest 246 OK (3 skipped)

**Explicitly deferred (next extract cycle — same helper pattern):**
- `_create_viral_hot_take`
- `_create_trending_commentary`
- Soft-fail helpers: `_create_motivational_moment_post`, `_create_emergency_unique_post`, `_create_fallback_post_for_duplicate`

**Acceptance:**
- ✅ Runtime dispatch via registry (weights, quality gate regen, duplicates equivalent)
- ✅ `post_strategies.py` remains free of bot imports
- ✅ News + dynamic + theme + poll + insight/prediction = extracted strategies via hybrid registry
- ⬜ Viral / soft-fail kinds still bound methods (interim) until next extract cycle

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

**Status:** ✅ Done — AI + RSS + ATProto/media (`orch-2026-10-19-17-34-strat-families` RETRY-003)

**Problem:** `RetryPolicy` / `classify_error` / `backoff_seconds` exist in `resilience_service` but are not consistently applied to all outbound I/O.

**Done:**
1. Catalog outbound call sites (ATProto, OpenRouter/Pollinations, RSS/HTTP, media) — in STRAT-003 plan
2. Inject `OutboundRetryPolicies` via `build_outbound_retry_policies` at composition root
3. OpenRouter / Pollinations use `retry_policy.execute`; RSS GET via `_http_get_text_with_retry`
4. Hermetic tests: `tests/test_retry_policy_retry002.py`
5. ATProto + media upload (+ engagement writes) use `RetryPolicy.execute` with bounded policies (RETRY-003)

**Acceptance (met):**
- ✅ Documented policy per wired adapter class
- ✅ Main loop does not reimplement ad-hoc retry for primary outbound paths
- ✅ No silent infinite retries (`max_retries` / `retry_budget` ≥ 1; CLIENT never retries)

---

## Phase 5 — Quality pipeline merge

**Status:** ✅ On scheduled-post path (`orch-2026-10-19-17-06-strat003-io`)

**Problem:** Dual quality paths — `QualityGate` (growth_engine) vs `ContentQualityAnalyzer` (ai_improvements) — overlap and confuse regen logic.

**Done:**
1. Unified interface in `app/quality_pipeline.py` (`QualityPipeline.evaluate` / `regenerate_until_quality`)
2. `create_scheduled_post` migrates regen to single entry; staged gate vs score
3. Tests: `tests/test_quality_pipeline_qual002.py`

**Acceptance (met for scheduled post):**
- ✅ One public quality entry point used by scheduled post path
- ✅ No divergent “passed gate A / failed gate B” surprises without explicit staging
- ✅ Tests for duplicate / low-signal / regen exhaustion

---

## Phase 6 — Shared HTTP session injection

**Status:** ✅ Done (`HTTP-001` + `HTTP-002` in `orch-2026-10-19-17-34-strat-families`)

**Problem:** `http_session` helpers exist, but not all adapters/services receive the shared `aiohttp.ClientSession` via ports; risk of extra sessions or lifecycle bugs.

**Done (HTTP-001):**
- `HttpSessionConsumer` port in `http_session.py`
- OpenRouter + Pollinations: constructor/`set_http_session` injection; no ad-hoc session in hot path when shared is live
- Bot owns lifecycle (`create` / `ensure` / `close`) and re-injects on ensure/recreate

**Done (HTTP-002):**
- Shared session injected into `bluesky_rich_posts.py` and `bluesky_post_formatter.py`
- No ad-hoc `ClientSession` in those hot paths when shared session is set
- Hermetic injection/ownership tests; smoke / unittest green

**Acceptance (met):**
- ✅ One owner for session lifecycle
- ✅ Adapters do not call `aiohttp.ClientSession()` ad hoc in hot paths when shared is live
- ✅ Packaging / smoke still green

---

## Phase 7 — Further bot slices (backlog)

**Status:** ⬜ **Deferred** — out of scope for `orch-2026-10-19-17-34-strat-families`; schedule a dedicated ≤10-task cycle

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
