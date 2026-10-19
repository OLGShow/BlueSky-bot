# Plan: STRAT-003 + RetryPolicy / Quality / Shared HTTP

**Created:** 2026-10-19 17:06  
**Orchestration:** `orch-2026-10-19-17-06-strat003-io`  
**Parent:** `orch-2026-10-19-15-06-godobj-p2` (registry dispatch done; STRAT-003 deferred)  
**Follow-up backlog:** `ai_docs/develop/plans/2026-10-19-god-object-decomposition-followup.md` (Phases 3 extract, 4–6)  
**ADR:** `ai_docs/develop/architecture/2026-10-19-layering-and-ports.md`  
**Audit:** `ai_docs/develop/audits/2026-10-19-architecture-and-layout.md` (Overall 6.5/10)  
**Status:** ✅ Complete  
**Goal:** Deep STRAT-003 (one strategy family fully off the bot + registry wire) + RetryPolicy on outbound I/O + unify quality pipeline on scheduled-post path + start shared HTTP session injection.  
**Priority:** High  
**Total Tasks:** 9  
**Estimated Time:** ~12–16 hours  
**Mode:** docs (plans enabled)

---

## Constraints (hard)

| Rule | Detail |
|------|--------|
| Import graph | `strategies/`, ports, services must **NOT** import `bluesky_bot_v2` |
| Config keys | Learning / A/B weight names stay **stable** (`_create_quality_news_post`, etc.) |
| Packaging | Update `PYFILES` in `packaging/sync-opt-from-sot.sh` + `packaging/build-deb.sh`; run opt sync for new modules/package |
| Verify | `python verify_bot.py --smoke` ; `python -m unittest discover -s tests -v` |
| Git | **No commits** in this orchestration (user commits later) |
| Scope | ≤10 tasks; leftover → update follow-up plan |

**Priority order if cut:** STRAT-003 core → RetryPolicy → quality merge → HTTP session.

---

## Tasks Overview

1. **STRAT-001** — Strategy package skeleton + news-family ports  
2. **STRAT-002** — Extract news/RSS family into `app/strategies/`  
3. **STRAT-003** — Registry wire + packaging sync for strategies  
4. **RETRY-001** — Catalog outbound I/O + inject RetryPolicy at composition root  
5. **RETRY-002** — Wire RetryPolicy on OpenRouter / Pollinations (+ one HTTP path)  
6. **QUAL-001** — Design unified quality pipeline interface  
7. **QUAL-002** — Migrate `create_scheduled_post` to single quality entry  
8. **HTTP-001** — Shared `ClientSession` injection start (adapters)  
9. **VERIFY-001** — Full verify gate + follow-up plan status update  

---

## Progress (updated by orchestrator)

- ✅ STRAT-001: Strategy package + news ports (Completed)
- ✅ STRAT-002: Extract news family (Completed) — `app/strategies/quality_news.py` (`QualityNewsStrategy`); bot thin-delegates; opt `strategies/` synced
- ✅ STRAT-003: Registry wire + packaging (Completed) — hybrid registry overwrites `_create_quality_news_post` with `QualityNewsStrategy`; learning key stable; `strategies/` synced in packaging
- ✅ RETRY-001: Catalog + inject RetryPolicy (Done)
- ✅ RETRY-002: Wire adapters + tests (Done) — OpenRouter/Pollinations use RetryPolicy.execute; RSS GET via `_http_get_text_with_retry`; hermetic tests in `tests/test_retry_policy_retry002.py`
- ✅ QUAL-001: Quality pipeline design (Done) — `app/quality_pipeline.py`
- ✅ QUAL-002: Migrate scheduled-post quality (Done) — `create_scheduled_post` → `regenerate_until_quality` / `QualityPipeline.evaluate`; staged gate vs score; tests `tests/test_quality_pipeline_qual002.py`
- ✅ HTTP-001: Shared HTTP session inject (Completed)
- ✅ VERIFY-001: Verify + follow-up docs (Completed) — smoke 2/2; unittest 193 OK (3 skipped); follow-up plan updated

### RETRY-001 catalog (outbound I/O → policy)

| # | Category | Call sites (module / symbol) | Current retry | Policy key | Breaker | Defaults (max_retries / budget) | Wire in |
|---|----------|------------------------------|---------------|------------|---------|----------------------------------|---------|
| 1 | ATProto | `bluesky_bot_v2`: `login`, `send_post`, `get_timeline`, `get_post_thread`, `app.bsky.actor.get_suggestions/get_profile`; `engagement_service` via ports (`like`/`repost`/`follow`) | Ad-hoc login retry only; writes mostly none | `retry_policies.atproto` (`bot.retry_atproto`) | `bluesky_api` | 3 / 10 | RETRY-002+ (engagement/ATProto paths) |
| 2 | OpenRouter | `openrouter_adapter.OpenRouterAI`: `_chat_completion` / `_generate_image` via `retry_policy.execute` | `RetryPolicy` (`retry_ai`) | `retry_policies.ai` (`bot.retry_ai`) | `ai_generation` | 3 / 10 | ✅ RETRY-002 |
| 3 | Pollinations | `pollinations_adapter.PollinationsAI`: `_make_request` / `_make_image_request` via `retry_policy.execute` | `RetryPolicy` (`retry_ai`) | `retry_policies.ai` (same AI policy) | `ai_generation` | 3 / 10 | ✅ RETRY-002 |
| 4 | RSS / HTTP GET | `bluesky_bot_v2._http_get_text_with_retry` (used by `fetch_external_content`); diagnostics/connectivity may still be one-shot; formatter leftovers | `retry_rss_http` on main RSS fetch | `retry_policies.rss_http` (`bot.retry_rss_http`) | `rss_fetch` | 2 / 8 | ✅ RETRY-002 (one path); formatter leftovers → follow-up |
| 5 | Media upload | `bluesky_bot_v2`: image download + `upload_blob` (~3444–3464, ~3579); `bluesky_rich_posts.upload_blob`; formatter `upload_blob` | None / ad-hoc session | `retry_policies.media_upload` (`bot.retry_media_upload`) | `bluesky_api` | 3 / 8 | later / optional with HTTP-001 |

**Where policies live:** built once in bot `__init__` via `build_outbound_retry_policies(...)` in `app/resilience_service.py`; held on `BlueSkyBotV2.retry_policies` (+ aliases). `ErrorClass.CLIENT` never retries. No infinite retry (`max_retries`/`retry_budget` must be ≥ 1).

---

## Dependencies Graph

```text
STRAT-001 → STRAT-002 → STRAT-003 ─┐
RETRY-001 → RETRY-002 ─────────────┼→ VERIFY-001
QUAL-001 → QUAL-002 ───────────────┤
HTTP-001 ──────────────────────────┘

Parallel after STRAT-001 (optional):
  STRAT-002 ‖ RETRY-001 ‖ QUAL-001 ‖ HTTP-001 (ports-only start)
STRAT-003 should finish before VERIFY-001; RETRY-002 / QUAL-002 / HTTP-001 before VERIFY-001.
```

---

## Task Details

### STRAT-001: Strategy package skeleton + news-family ports
- **Priority:** Critical  
- **Complexity:** Moderate  
- **Time:** ~1.5h  
- **Dependencies:** None  
- **Agent:** worker → test-writer  
- **Files:** `app/strategies/__init__.py`, `app/strategies/ports.py` (or `deps.py`), maybe `app/strategies/README.md` (short only if needed)

**Work:**
1. Create package `app/strategies/` with no import of `bluesky_bot_v2`.
2. Inventory `_create_quality_news_post` and its private helpers (RSS fetch, fallbacks to opinion, image/link helpers it calls).
3. Define narrow Protocol/dataclass deps the news strategy needs (e.g. RSS headlines, content generation, image attach, config view, regen-mode flag) — same DIP style as `content_ports.py` / `engagement_ports.py`.
4. Re-export nothing that pulls the bot; keep `post_strategies.PostStrategy` as the strategy contract.

**Acceptance:**
- [x] Package imports cleanly without `bluesky_bot_v2`
- [x] News-family dependency surface documented in ports module docstrings
- [x] Hermetic smoke import test or unittest for ports module

---

### STRAT-002: Extract news/RSS family into `app/strategies/`
- **Priority:** Critical  
- **Complexity:** Complex  
- **Time:** ~3–4h  
- **Dependencies:** STRAT-001  
- **Agent:** worker → test-writer → reviewer  
- **Files:** `app/strategies/news.py` (name flexible), thin leftovers in `app/bluesky_bot_v2.py`

**Work:**
1. Move `_create_quality_news_post` body (and **only** helpers that are news-specific / safely movable) into a class implementing `PostStrategy.create`.
2. Inject ports from STRAT-001; no `self.bot`.
3. Leave other `_create_*` methods on the bot for later cycles (incremental family extract).
4. Prefer fallbacks via injected callables/ports rather than calling sibling bot methods by name.

**Acceptance:**
- [x] At least one config family fully lives under `app/strategies/` (news/RSS)
- [x] Strategy module does not import `bluesky_bot_v2`
- [x] Behavior preserved for happy path + soft RSS miss → fallback (covered by tests or documented parity notes)
- [ ] Unit tests with fakes for ports — handoff to test-writer

**Done (STRAT-002):**
- Module: `app/strategies/quality_news.py`
- Class: `QualityNewsStrategy(ports: NewsStrategyPorts)` with `async create()`
- Constant: `STRATEGY_NAME = "_create_quality_news_post"`
- Bot: `_build_news_strategy_ports()` + `self.quality_news_strategy`; `_create_quality_news_post` thin-delegates
- Packaging: `strategies/` dir sync in sync-opt + build-deb; opt mirror updated

---

### STRAT-003: Registry wire + packaging for strategies
- **Priority:** Critical  
- **Complexity:** Moderate  
- **Time:** ~1.5h  
- **Dependencies:** STRAT-002  
- **Agent:** worker → test-writer  
- **Files:** `app/bluesky_bot_v2.py` (`_build_post_strategy_registry` / `build_bound_registry` call site), `app/post_strategies.py` (if helper needed), `packaging/sync-opt-from-sot.sh`, `packaging/build-deb.sh`

**Work:**
1. At composition root, register extracted news strategy under the **same** config key string (`_create_quality_news_post`).
2. Other keys may remain bound methods via `build_bound_registry` (hybrid registry OK this cycle).
3. Packaging: flat SoT today — either sync `strategies/` as a package directory into `opt/bluesky-bot/strategies/`, or list strategy modules in `PYFILES` consistently in **both** sync + build-deb scripts. Prefer package dir sync so imports stay `from strategies.news import …` when cwd/`PYTHONPATH` is the deploy root.
4. Run `bash packaging/sync-opt-from-sot.sh` (or document Windows equivalent) so opt mirror matches.

**Acceptance:**
- [x] Runtime registry resolves `_create_quality_news_post` to extracted strategy (not bound method)
- [x] Learning/A/B still key by string `_create_quality_news_post`
- [x] Packaging lists/syncs new modules; opt sync succeeds
- [x] Existing registry unit tests updated; no import cycle

**Done (STRAT-003):**
- `_build_post_strategy_registry`: after `build_bound_registry`, `register(STRATEGY_NAME, self.quality_news_strategy, overwrite=True)`
- Thin `_create_quality_news_post` kept for getattr; registry prefers instance
- Test: `test_hybrid_overwrite_prefers_extracted_strategy_instance`
- Packaging: `strategies/` dir sync already in sync-opt + build-deb

---

### RETRY-001: Catalog outbound I/O + inject RetryPolicy ✅
- **Priority:** High  
- **Complexity:** Moderate  
- **Time:** ~1.5h  
- **Dependencies:** None (parallel with STRAT-*)  
- **Agent:** worker → documenter (short note in plan/report)  
- **Files:** `app/resilience_service.py` (factory), `app/bluesky_bot_v2.py` (composition), catalog table in Progress above

**Work:**
1. Catalog outbound call sites: ATProto client, OpenRouter, Pollinations, RSS/HTTP gets, Bluesky media upload.
2. Create shared / per-adapter `RetryPolicy` (+ optional `CircuitBreaker`) at composition root — do **not** put retry loops in the main schedule loop for those paths.
3. Document policy defaults (max_retries, budget, which ErrorClass does not retry — CLIENT already short-circuits).

**Acceptance:**
- [x] Written catalog (table in this plan Progress notes or architecture note) of adapter → policy
- [x] Bot holds injectable policy instances (or builds them once for adapters)
- [x] No silent infinite retries by design

---

### RETRY-002: Wire RetryPolicy on key adapters + tests
- **Priority:** High  
- **Complexity:** Moderate  
- **Time:** ~2h  
- **Dependencies:** RETRY-001  
- **Agent:** worker → test-writer → test-runner  
- **Files:** `app/openrouter_adapter.py`, `app/pollinations_adapter.py`, optionally one bot HTTP fetch helper or RSS path; `tests/test_retry_policy_*.py`

**Work:**
1. Wrap outbound calls in OpenRouter + Pollinations with `RetryPolicy.execute`.
2. Wire at least one shared-session HTTP GET path (RSS or image download) the same way — prefer adapter/helper over main loop.
3. Hermetic tests: fake failing async fn → success after N; exhaust retries; CLIENT errors not retried.

**Acceptance:**
- [x] OpenRouter + Pollinations use RetryPolicy (not ad-hoc sleep loops for those calls)
- [x] Tests cover success-after-retry and budget/exhaust
- [x] Main loop does not reimplement the same retry for those adapters

---

### QUAL-001: Design unified quality pipeline
- **Priority:** High  
- **Complexity:** Moderate  
- **Time:** ~1.5h  
- **Dependencies:** None  
- **Agent:** senior-reviewer (brief) → worker  
- **Files:** new `app/quality_pipeline.py` (or extend `growth_engine.py` with facade), design notes in module docstring

**Work:**
1. Document current split:
   - `QualityGate.check` — pre-publish regen loop (signal/fluff/semantic dup)
   - `ContentQualityAnalyzer` via `_evaluate_post_quality` — viral score / triggers after gate
2. Design single public entry, e.g. `QualityPipeline.evaluate(text, context) -> QualityResult` with stages (gate → score) and stable reason codes.
3. Keep config namespaces initially (`quality_gate_settings`, `viral_content_settings`) but one code path; optional later merge of config keys.

**Acceptance:**
- [x] One documented public interface for scheduled-post quality
- [x] Mapping of old call sites → new stages written
- [x] No behavior change yet required in this task (design + facade OK); QUAL-002 migrates

---

### QUAL-002: Migrate scheduled-post path to unified quality
- **Priority:** High  
- **Complexity:** Moderate  
- **Time:** ~2h  
- **Dependencies:** QUAL-001  
- **Agent:** worker → test-writer → test-runner  
- **Files:** `app/bluesky_bot_v2.py` (`create_scheduled_post`, `_evaluate_post_quality`), `app/quality_pipeline.py`, tests

**Work:**
1. Replace dual use in `create_scheduled_post` (gate regen loop + `_evaluate_post_quality`) with the unified pipeline.
2. Preserve regen semantics (`max_regen`, `_quality_gate_regen_mode` / equivalent port).
3. Tests: duplicate/low-signal fail → regen; viral threshold fail; regen exhaustion → no publish.

**Acceptance:**
- [x] Scheduled post path uses one public quality entry point
- [x] No divergent “passed gate A / failed gate B” without explicit staged reasons in result
- [x] Unittest coverage for duplicate / low-signal / regen exhaustion

---

### HTTP-001: Shared ClientSession injection (start)
- **Priority:** Medium  
- **Complexity:** Moderate  
- **Time:** ~2h  
- **Dependencies:** None (can start after STRAT-001; finish before VERIFY)  
- **Agent:** worker → test-writer  
- **Files:** `app/http_session.py` (optional port), `app/openrouter_adapter.py`, `app/pollinations_adapter.py`, `app/bluesky_bot_v2.py` wiring; note leftover ad-hoc sessions in `bluesky_rich_posts.py` / `bluesky_post_formatter.py` for follow-up

**Work:**
1. Add narrow session provider/port (or constructor injection of `aiohttp.ClientSession`).
2. Stop OpenRouter/Pollinations from owning a private `ClientSession()` in hot paths when bot already has `http_session` — inject shared session + keep lifecycle ownership on bot (`create` / `ensure` / `close`).
3. Defer formatter/rich_posts ad-hoc sessions to follow-up if timeboxed.

**Acceptance:**
- [x] OpenRouter + Pollinations use injected/shared session (no new ad-hoc session per call when shared is live)
- [x] Single owner for create/recreate/close remains the bot (or thin HttpSessionOwner)
- [x] Test: recreate-after-close / no use-after-close for injected path
- [x] Leftovers documented in follow-up plan

---

### VERIFY-001: Verify gate + follow-up plan update
- **Priority:** Critical  
- **Complexity:** Simple  
- **Time:** ~1h  
- **Dependencies:** STRAT-003, RETRY-002, QUAL-002, HTTP-001  
- **Agent:** test-runner → documenter  

**Work:**
1. Run:
   ```bash
   python verify_bot.py --smoke
   python -m unittest discover -s tests -v
   ```
2. Update `ai_docs/develop/plans/2026-10-19-god-object-decomposition-followup.md`: Phase 3 extract / 4 / 5 / 6 status; list deferred items (remaining strategy families, formatter sessions, Phase 7 slices).
3. No git commit.

**Acceptance:**
- [x] Smoke 2/2 (or current expected count) green
- [x] Unittest suite green (skips OK if pre-existing) — 193 ran, 3 skipped
- [x] Follow-up plan reflects done vs deferred
- [x] Import grep: no `bluesky_bot_v2` under `app/strategies/`

---

## Architecture Decisions (this cycle)

1. **Hybrid registry:** Extracted `PostStrategy` instances for news; bound methods remain for other config keys until later families extract.
2. **Stable strategy name keys:** Registry registration name == config / learning / A/B string (e.g. `_create_quality_news_post`).
3. **Retry at adapters:** `RetryPolicy.execute` wraps I/O adapters; orchestration loop stays thin.
4. **Quality staging:** One facade; internal stages may still use QualityGate heuristics + ContentQualityAnalyzer scoring, but callers see one API.
5. **HTTP ownership:** Bot (composition root) owns session lifecycle; adapters receive session via injection.

---

## Implementation Notes

- First family = **news/RSS** (`_create_quality_news_post`, weight ~0.4) — highest leverage.
- Do not flatten strategy logic back into bot “for convenience”; prefer ports.
- Packaging is flat today — package sync for `strategies/` must be explicit in both packaging scripts.
- Prefer hermetic fakes over live network in new tests.
- If scope slips: finish STRAT-001…003 + RETRY-001…002; park QUAL-002 or HTTP-001 details in follow-up with clear checkboxes.

---

## Risks

| Risk | Mitigation |
|------|------------|
| News extract pulls half the bot via helpers | Narrow ports; leave image/opinion as injected callables |
| Packaging breaks package imports | Sync `strategies/` dir; verify smoke import path |
| Quality unify changes publish rate | Preserve thresholds; staged reasons; dry-run compare later |
| Retry doubles backoff with outer loop | Wire only adapter layer; grep for duplicate sleep/retry |
| Config key rename breaks learning | Never rename keys this cycle |

---

## Deferred (explicitly out of this orch)

- Remaining `_create_*` families (opinion, tip, discussion, viral, …)
- Ad-hoc `ClientSession` in `bluesky_rich_posts.py` / `bluesky_post_formatter.py`
- Phase 7 bot slices (state / schedule / learning façades)
- Config namespace merge for quality settings (optional cleanup)

---

## References

- Follow-up: `ai_docs/develop/plans/2026-10-19-god-object-decomposition-followup.md`
- Phase 2 report: `ai_docs/develop/reports/2026-10-19-god-object-phase2-content-strategies-implementation.md`
- ADR-001: `ai_docs/develop/architecture/2026-10-19-layering-and-ports.md`
- Audit: `ai_docs/develop/audits/2026-10-19-architecture-and-layout.md`
- Registry: `app/post_strategies.py`
- Resilience: `app/resilience_service.py`
- HTTP: `app/http_session.py`
