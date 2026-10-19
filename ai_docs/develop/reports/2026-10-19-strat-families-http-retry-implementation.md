# Report: Remaining Strategy Families + HTTP/Retry Leftovers

**Date:** 2026-10-19  
**Orchestration:** orch-2026-10-19-17-34-strat-families  
**Status:** ✅ Completed  
**Plan:** [2026-10-19-strat-families-http-retry.md](../plans/2026-10-19-strat-families-http-retry.md)  
**Follow-up:** [2026-10-19-god-object-decomposition-followup.md](../plans/2026-10-19-god-object-decomposition-followup.md)  
**ADR:** [2026-10-19-layering-and-ports.md](../architecture/2026-10-19-layering-and-ports.md)  
**Audit:** [2026-10-19-architecture-and-layout.md](../audits/2026-10-19-architecture-and-layout.md)  
**Prior orch:** orch-2026-10-19-17-06-strat003-io

## Summary

Finished God Object Phase 3–6 leftovers: extracted remaining default-weight strategy families into `app/strategies/` (shared image/theme helper → dynamic / theme / poll / insight+prediction), closed Phase 6 shared HTTP for formatter/rich_posts, and wired Phase 4 `RetryPolicy` on ATProto + media upload. Must-fix during review: list-strategy fallback used literal `\\n` — fixed to real newlines (app + opt). Verify gate: **smoke 2/2**; **unittest 246 OK (3 skipped)**. Viral family + Phase 7 deferred. No git commit / no archive.

## What Was Built

### Strategy families (STRAT-004…008)

- **STRAT-004:** Shared image/theme ports + `ImagePostHelper` (`app/strategies/image_post.py`, ports in `ports.py`); bot thin-delegates; hermetic fakes (`tests/test_image_post_helper_strat004.py`).
- **STRAT-005:** Dynamic family — `PersonalOpinionStrategy`, `QualityTipStrategy`, `QualityDiscussionStrategy` in `dynamic_posts.py`; hybrid overwrite for three stable keys; tests in `test_dynamic_posts_strat005.py`.
- **STRAT-006:** Theme family — `QualityAiInsightStrategy`, `QualityListStrategy` in `theme_posts.py`; theme pick + structured + image/fallback; tests in `test_theme_posts_strat006.py`.
- **STRAT-007:** `QualityPollStrategy` in `poll_post.py`; `PollFactoryPort` / `PollStrategyPorts`; registry key `_create_quality_poll_post`; create_poll parity tests.
- **STRAT-008:** `PersonalInsightStrategy` + `PredictionStrategy` in `insight_posts.py`; hybrid overwrite; viral/trending left on bot.

### List-fallback newline fix (review must-fix)

- `_build_list_fallback` in `theme_posts.py` published literal `\\n` instead of real newlines (AI-insight fallback was already correct).
- Fixed in `app/strategies/theme_posts.py` + `opt/bluesky-bot/strategies/theme_posts.py`; test expectation in `test_empty_structured_uses_fallback` aligned.

### Shared HTTP (HTTP-002)

- Formatter + rich_posts consume injected shared `ClientSession`; bot injects via `_inject_http_session_into_adapters`.
- Hermetic ownership/injection tests: `tests/test_http_session_http002.py`.

### RetryPolicy (RETRY-003)

- `retry_atproto` / `retry_media_upload` wired on ATProto + media (+ engagement write paths as applicable); bounded retries; `ErrorClass.CLIENT` no-retry.
- Hermetic tests: `tests/test_retry_policy_retry003.py`.

### Packaging (PKG-001)

- Directory-based `strategies/*.py` sync confirmed in `sync-opt-from-sot.sh` / `build-deb.sh`.
- Ran opt mirror (32 files); all 8 strategy modules identical under `opt/bluesky-bot/strategies/`; `PYFILES` unchanged.

### Verification (VERIFY-001)

- Smoke: `python verify_bot.py --smoke` — **2/2 passed**
- Unittest: `python -m unittest discover -s tests -v` — **246 OK (3 skipped)** (`tasks.json` also records 248 run/passed including skips accounting)
- Follow-up plan updated: Phase 3 most families done; Phase 4 ATProto/media done; Phase 6 complete; **Phase 7 deferred**; viral + soft-fail helpers listed

## Completed Tasks

1. ✅ **STRAT-004:** Shared image/theme ports + `ImagePostHelper`
2. ✅ **STRAT-005:** Dynamic family (opinion + tip + discussion)
3. ✅ **STRAT-006:** Theme family (ai_insight + list) + list-fallback newline fix
4. ✅ **STRAT-007:** Poll family extract
5. ✅ **STRAT-008:** Insight + prediction family (viral deferred)
6. ✅ **HTTP-002:** Shared session → formatter / rich_posts
7. ✅ **RETRY-003:** RetryPolicy on ATProto + media upload
8. ✅ **PKG-001:** Packaging strategies sync + opt mirror
9. ✅ **VERIFY-001:** Smoke 2/2; unittest 246 OK (3 skipped); follow-up refreshed

## Technical Decisions

- **ImagePostHelper first:** one glue layer for image/blob/formatter reused by STRAT-005…008.
- **Hybrid registry continues:** `build_bound_registry` then `overwrite=True` per extracted `STRATEGY_NAME`.
- **Stable config keys:** learning/A/B strings unchanged (`_create_personal_opinion_post`, etc.).
- **Import graph:** `strategies/` must not import `bluesky_bot_v2`.
- **Viral + emergency helpers deferred:** not on default weight table; thin bot methods until next cycle.
- **Phase 7 deferred:** scheduler / learning / state need a separate ≤10-task orch.

## Metrics

| Metric | Value |
|--------|-------|
| Tasks | **9/9** completed |
| Smoke | **2/2** passed |
| Unittest | **246** OK, **3** skipped, **0** failed |
| Strategy modules under `app/strategies/` | **8** (incl. news + new families) |
| Estimated effort | 14–18 h (plan) |
| Prior orch | orch-2026-10-19-17-06-strat003-io |
| Git commit | **None** (hard constraint) |

## Known Issues / Leftovers

- **Viral family** — `_create_viral_hot_take`, `_create_trending_commentary` still on bot.
- **Soft-fail helpers** — motivational / emergency / fallback-for-duplicate still on bot.
- **Phase 7** — scheduler / learning / state façades deferred.
- **God Object LOC** — methods thin-delegated, but file still large; formal re-score TBD.
- **Dual quality** — `QualityGate` vs `ContentQualityAnalyzer` still coexist under `QualityPipeline` facade.

## Related Documentation

- Plan: [2026-10-19-strat-families-http-retry.md](../plans/2026-10-19-strat-families-http-retry.md)
- Follow-up: [2026-10-19-god-object-decomposition-followup.md](../plans/2026-10-19-god-object-decomposition-followup.md)
- ADR: [2026-10-19-layering-and-ports.md](../architecture/2026-10-19-layering-and-ports.md)
- Audit: [2026-10-19-architecture-and-layout.md](../audits/2026-10-19-architecture-and-layout.md)
- Prior report: [2026-10-19-strat003-retry-quality-http-implementation.md](./2026-10-19-strat003-retry-quality-http-implementation.md)
- Workspace: `.cursor/workspace/active/orch-2026-10-19-17-34-strat-families/` (`progress.json`, `tasks.json`, `links.json`)

## Next Steps

1. Extract viral + soft-fail strategy leftovers (same ImagePostHelper pattern).
2. Phase 7: scheduler / learning / state slices (own ≤10-task cycle).
3. Optional formal architecture re-score after Phase 3–6 drivers landed.
4. Plan and tasks ready for archival (orchestrator; documenter does not archive).
