# Plan: Remaining Strategy Families + HTTP/Retry Leftovers

**Created:** 2026-10-19 17:34  
**Orchestration:** `orch-2026-10-19-17-34-strat-families`  
**Parent / follow-up:** `ai_docs/develop/plans/2026-10-19-god-object-decomposition-followup.md`  
**Prior cycle:** `orch-2026-10-19-17-06-strat003-io` (QualityNewsStrategy + AI/RSS retry + QualityPipeline + HTTP AI adapters)  
**ADR:** `ai_docs/develop/architecture/2026-10-19-layering-and-ports.md`  
**Status:** ✅ Completed  
**Goal:** Extract remaining `_create_*` strategy families into `app/strategies/` (shrink God Object), finish Phase 6 HTTP for formatter/rich_posts, finish Phase 4 ATProto/media RetryPolicy. Phase 7 deferred.  
**Priority:** High (P0 strategies → P1 HTTP → P1 retry)  
**Total Tasks:** 9  
**Estimated Time:** ~14–18 hours  
**Mode:** docs (plans enabled)

---

## Constraints (hard)

| Rule | Detail |
|------|--------|
| Import graph | `strategies/` must **NOT** import `bluesky_bot_v2` |
| Config / learning keys | Stable names: `_create_personal_opinion_post`, `_create_quality_tip_post`, `_create_quality_discussion`, `_create_quality_ai_insight`, `_create_quality_list_post`, `_create_quality_poll_post`, `_create_prediction_post`, `_create_personal_insight`, etc. |
| Pattern | Copy `app/strategies/quality_news.py` + ports + thin bot delegate + hybrid registry `overwrite=True` |
| Packaging | `strategies/` sync in `packaging/sync-opt-from-sot.sh` + `build-deb.sh`; run opt mirror |
| Verify | `python verify_bot.py --smoke` ; `python -m unittest discover -s tests -v` |
| Git | **No commits** in this orchestration |
| Scope | ≤10 tasks; Phase 7 **deferred** to follow-up update |

**Cut order if over budget:** drop STRAT-008 first → keep STRAT-004..007 + HTTP-002 + RETRY-003 + PKG + VERIFY.

---

## Inventory (remaining after QualityNewsStrategy)

| Family | Bot methods (SoT: `app/bluesky_bot_v2.py`) | Pattern | This cycle |
|--------|---------------------------------------------|---------|------------|
| Shared helper | `_create_post_with_image_generation`, `_quality_theme_post` | Image + structured content | STRAT-004 |
| Dynamic | `_create_personal_opinion_post`, `_create_quality_tip_post`, `_create_quality_discussion` | `dynamic_generator` + image helper | STRAT-005 |
| Theme | `_create_quality_ai_insight`, `_create_quality_list_post` | themes + `_quality_theme_post` | STRAT-006 |
| Poll | `_create_quality_poll_post` | structured + `formatter.create_poll` | STRAT-007 |
| Insight / prediction | `_create_personal_insight`, `_create_prediction_post` | theme list + image helper | STRAT-008 |
| Viral (defer) | `_create_viral_hot_take`, `_create_trending_commentary` | same as insight | **follow-up** |
| Fallback helpers (defer) | `_create_motivational_moment_post`, `_create_emergency_unique_post`, `_create_fallback_post_for_duplicate` | used as soft-fail paths | **follow-up** (thin bot OK) |

Default weighted keys (news already extracted): opinion, ai_insight, tip, discussion — covered by STRAT-005/006. List/poll/prediction/insight covered by STRAT-006..008.

---

## Tasks Overview

1. **STRAT-004** — Shared image/theme ports + `ImagePostHelper`  
2. **STRAT-005** — Dynamic family (opinion + tip + discussion)  
3. **STRAT-006** — Theme family (ai_insight + list)  
4. **STRAT-007** — Poll family  
5. **STRAT-008** — Insight + prediction family  
6. **HTTP-002** — Shared session → formatter / rich_posts (Phase 6 finish)  
7. **RETRY-003** — RetryPolicy on ATProto + media upload (Phase 4 finish)  
8. **PKG-001** — Packaging `strategies/` sync + opt mirror  
9. **VERIFY-001** — Smoke + unittest + follow-up plan update (Phase 7 deferred note)  

---

## Progress (updated by orchestrator)

- ✅ STRAT-004: Shared image/theme ports + helper (Done)
- ✅ STRAT-005: Dynamic family (Done)
- ✅ STRAT-006: Theme family (Done)
- ✅ STRAT-007: Poll family (Done)
- ✅ STRAT-008: Insight + prediction (Done)
- ✅ HTTP-002: Formatter / rich_posts HTTP session (Done)
- ✅ RETRY-003: ATProto + media RetryPolicy (Done)
- ✅ PKG-001: Packaging sync (Done)
- ✅ VERIFY-001: Verify gate + docs (Done) — smoke 2/2; unittest 246 OK (3 skipped); follow-up updated

---

## Dependencies Graph

```text
STRAT-004 → STRAT-005 ─┐
         → STRAT-006 ─┤
         → STRAT-007 ─┼→ PKG-001 → VERIFY-001
         → STRAT-008 ─┤
HTTP-002 ─────────────┤
RETRY-003 ────────────┘

Parallel after STRAT-004:
  STRAT-005 ‖ STRAT-006 ‖ STRAT-007 ‖ STRAT-008
  HTTP-002 ‖ RETRY-003 (independent of strategy extracts)
```

Phase 7 (scheduler / learning / state) — **out of scope**; note in VERIFY-001 follow-up update only.

---

## Task Details

### STRAT-004: Shared image/theme ports + ImagePostHelper
- **Priority:** Critical (P0)  
- **Complexity:** Complex  
- **Time:** ~2.5h  
- **Dependencies:** None  
- **Agent:** worker → test-writer  
- **Files:** `app/strategies/ports.py` (extend), `app/strategies/image_post.py` (or similar), thin wrappers in `app/bluesky_bot_v2.py`

**Work:**
1. Inventory deps of `_create_post_with_image_generation` and `_quality_theme_post` (structured content, image prompt, Pollinations, blob upload, formatter `create_post`, emergency fallback).
2. Add shared Protocols/dataclasses (e.g. `ImagePostPorts`, `ThemePostPorts`, callable adapters) — **no** `bluesky_bot_v2` import.
3. Extract helper class(es) used by later families; bot builds ports at composition root and keeps thin delegates for any still-bound callers.
4. Hermetic unit tests with fakes (happy path + empty content → fallback + image miss → text-only).

**Acceptance:**
- [x] Helper module imports without `bluesky_bot_v2`
- [x] Ports document bot→port mapping (same style as `NewsStrategyPorts`)
- [x] Bot image-post path still works via thin delegate / ports
- [x] Unittest covers helper with fakes

---

### STRAT-005: Dynamic family (opinion + tip + discussion)
- **Priority:** Critical (P0)  
- **Complexity:** Complex  
- **Time:** ~3h  
- **Dependencies:** STRAT-004  
- **Agent:** worker → test-writer → reviewer  
- **Files:** `app/strategies/dynamic_posts.py` (name flexible), `app/strategies/__init__.py`, `app/bluesky_bot_v2.py`, `app/post_strategies.py` (hybrid overwrite only)

**Work:**
1. Ports for `dynamic_generator.generate_dynamic_content` / fallback + `ImagePostHelper` + emergency fallback.
2. Extract `PersonalOpinionStrategy`, `QualityTipStrategy`, `QualityDiscussionStrategy` (or one module with three classes) implementing `PostStrategy.create`.
3. Stable `STRATEGY_NAME` constants matching config keys.
4. Composition root: build instances; hybrid registry `overwrite=True` for each key; bot methods thin-delegate.
5. Tests: each strategy create path with fakes; import-acyclic check.

**Acceptance:**
- [x] Three config keys resolve to extracted strategy instances (not bound bot methods)
- [x] Learning / weight keys unchanged
- [x] No `strategies` → `bluesky_bot_v2` import
- [x] Hermetic tests green for the three strategies

---

### STRAT-006: Theme family (ai_insight + list)
- **Priority:** Critical (P0)  
- **Complexity:** Moderate  
- **Time:** ~2h  
- **Dependencies:** STRAT-004  
- **Agent:** worker → test-writer  
- **Files:** `app/strategies/theme_posts.py`, bot thin delegates, registry overwrites

**Work:**
1. Move `_quality_theme_post` logic + `_create_quality_ai_insight` / `_create_quality_list_post` prompts/themes into strategies (reuse ImagePostHelper).
2. Register under `_create_quality_ai_insight` and `_create_quality_list_post`.
3. Thin bot delegates; tests with fakes.

**Acceptance:**
- [x] Both keys overwritten in hybrid registry
- [x] Theme pick + structured + image/fallback parity with bot behavior
- [x] Hermetic tests green

---

### STRAT-007: Poll family
- **Priority:** High (P0)  
- **Complexity:** Moderate  
- **Time:** ~1.5h  
- **Dependencies:** STRAT-004 (ports style; may need only structured + formatter poll port)  
- **Agent:** worker → test-writer  
- **Files:** `app/strategies/poll_post.py`, bot, registry

**Work:**
1. Ports: structured content + `formatter.create_poll` (do not pull full formatter into strategy).
2. Extract `QualityPollStrategy`; registry key `_create_quality_poll_post`.
3. Thin delegate + hermetic test (poll options / duration preserved).

**Acceptance:**
- [x] Registry uses extracted poll strategy
- [x] `create_poll` called with question/options/duration/content_type parity
- [x] Hermetic test green

---

### STRAT-008: Insight + prediction family
- **Priority:** High (P0)  
- **Complexity:** Moderate  
- **Time:** ~2h  
- **Dependencies:** STRAT-004  
- **Agent:** worker → test-writer  
- **Files:** `app/strategies/insight_posts.py` (or split), bot, registry

**Work:**
1. Extract `_create_personal_insight` and `_create_prediction_post` via ImagePostHelper + structured content ports.
2. Stable keys; hybrid overwrite; thin delegates.
3. **Out of scope here:** viral_hot_take / trending_commentary (document in follow-up).

**Acceptance:**
- [x] Both keys registered as extracted strategies
- [x] Hermetic tests green
- [x] Viral family explicitly deferred in follow-up plan note

---

### HTTP-002: Shared ClientSession → formatter / rich_posts
- **Priority:** High (P1)  
- **Complexity:** Moderate  
- **Time:** ~2h  
- **Dependencies:** None (parallel with STRAT-*)  
- **Agent:** worker → test-writer  
- **Files:** `app/bluesky_post_formatter.py`, `app/bluesky_rich_posts.py`, `app/http_session.py` (if needed), `app/bluesky_bot_v2.py` (`_inject_http_session_into_adapters`)

**Work:**
1. Replace ad-hoc `aiohttp.ClientSession()` in formatter `add_image_to_post` and rich_posts `fetch_link_metadata` / `create_media_gallery_post` with injected shared session (`HttpSessionConsumer` / `set_http_session` or ctor).
2. Bot owns lifecycle; re-inject on `ensure` / recreate (extend `_inject_http_session_into_adapters`).
3. Fallback: if no shared session, create once with clear ownership flag (same pattern as OpenRouter) — prefer never ad-hoc in hot path when bot session is live.
4. Tests: inject fake/session mock; recreate-after-close path if feasible hermetically.

**Acceptance:**
- [x] No ad-hoc `ClientSession()` in formatter/rich_posts hot paths when shared session is set
- [x] Bot injects session into formatter + rich_posts
- [x] Hermetic test(s) for injection / no double-close ownership bugs

---

### RETRY-003: RetryPolicy on ATProto + media upload
- **Priority:** High (P1)  
- **Complexity:** Moderate–Complex  
- **Time:** ~2.5h  
- **Dependencies:** None (policies already built: `retry_atproto`, `retry_media_upload`)  
- **Agent:** worker → test-writer  
- **Files:** `app/bluesky_bot_v2.py` (upload_blob / send paths), possibly engagement write ports, `tests/test_retry_policy_*.py`

**Work:**
1. Wire `bot.retry_atproto.execute` around primary ATProto write/read call sites that still lack policy (catalog from prior RETRY-001: login leftovers, `send_post`, timeline/thread where appropriate, engagement writes if still ad-hoc).
2. Wire `bot.retry_media_upload.execute` around image download + `upload_blob` paths (~media upload helpers).
3. Do **not** infinite-retry; respect `ErrorClass.CLIENT`; keep breaker `bluesky_api` where already attached.
4. Hermetic tests with fake failing-then-succeeding callables (extend `tests/test_retry_policy_retry002.py` or new `retry003`).

**Acceptance:**
- [x] Media upload / ATProto primary paths use `RetryPolicy.execute` (no new ad-hoc sleep loops)
- [x] Policies remain bounded (`max_retries` / `retry_budget` ≥ 1)
- [x] Hermetic tests prove retry + CLIENT no-retry

---

### PKG-001: Packaging strategies sync + opt mirror
- **Priority:** High  
- **Complexity:** Simple  
- **Time:** ~0.5h  
- **Dependencies:** STRAT-004..008 (new modules exist)  
- **Agent:** worker  
- **Files:** `packaging/sync-opt-from-sot.sh`, `packaging/build-deb.sh`, `opt/bluesky-bot/strategies/`

**Work:**
1. Confirm `strategies/` directory sync loops cover all new `*.py` (already directory-based — verify still correct).
2. Run `bash packaging/sync-opt-from-sot.sh` (or Windows-equivalent) so `opt/bluesky-bot/strategies/` mirrors SoT.
3. If any top-level `app/*.py` SoT modules added outside `strategies/`, add to `PYFILES` arrays.

**Acceptance:**
- [x] Every new strategy module present under `opt/bluesky-bot/strategies/`
- [x] `PYFILES` / strategies sync scripts unchanged-or-updated consistently
- [x] No missing SoT module for runtime imports

---

### VERIFY-001: Full verify gate + follow-up docs
- **Priority:** Critical  
- **Complexity:** Simple  
- **Time:** ~1h  
- **Dependencies:** STRAT-005..008, HTTP-002, RETRY-003, PKG-001  
- **Agent:** test-runner → documenter (light)  
- **Files:** follow-up plan status section; this plan progress checkboxes

**Work:**
1. Run `python verify_bot.py --smoke`
2. Run `python -m unittest discover -s tests -v`
3. Update `ai_docs/develop/plans/2026-10-19-god-object-decomposition-followup.md`: mark Phase 3 remaining families / Phase 4 ATProto-media / Phase 6 formatter as done (or partial); **Phase 7 deferred** + list viral/fallback leftovers.
4. No git commit.

**Acceptance:**
- [x] Smoke passes (2/2)
- [x] Unittest discover passes — 246 OK (3 skipped)
- [x] Follow-up plan updated; Phase 7 explicitly deferred
- [x] No commit created by agents

---

## Architecture Decisions

- **Hybrid registry continues:** `build_bound_registry` then `overwrite=True` per extracted `STRATEGY_NAME` (same as QualityNewsStrategy).
- **Shared ImagePostHelper first:** avoids duplicating image/blob/formatter glue across 4 family tasks.
- **Batch by pattern, not one method per task:** stays ≤10 tasks while maximizing family coverage.
- **Phase 7 deferred:** scheduler / learning / state slices need their own ≤10-task cycle.
- **Viral + emergency helpers deferred:** not on default weight table; keep thin bot methods until next extract cycle.

## Implementation Notes

- Prefer extending `app/strategies/ports.py` over a second ports package.
- Re-export new strategies from `app/strategies/__init__.py`.
- When wiring fallbacks between strategies (e.g. news → opinion), inject `FallbackPostPort` / bound `create` — never import bot.
- After extracts, God Object methods should be ≤3-line delegates where possible.

## Risks

| Risk | Mitigation |
|------|------------|
| Image helper extract breaks poll/news paths | Keep news on existing ports; poll uses separate formatter port |
| Registry overwrite misses a key | Assert registered names in tests; keep bound fallback until overwrite succeeds |
| HTTP inject double-close | Ownership flag / shared-only; mirror OpenRouter pattern |
| ATProto retry changes engagement rate | Hermetic first; dry-run compare optional; bounded retries only |
| Scope creep into Phase 7 | VERIFY-001 only documents deferral |

## References

- Pattern: `app/strategies/quality_news.py`, `app/strategies/ports.py`
- Prior plan: `ai_docs/develop/plans/2026-10-19-strat003-retry-quality-http.md`
- Follow-up: `ai_docs/develop/plans/2026-10-19-god-object-decomposition-followup.md`
- ADR: `ai_docs/develop/architecture/2026-10-19-layering-and-ports.md`
