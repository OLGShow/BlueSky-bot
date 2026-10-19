# Report: STRAT-003 + RetryPolicy / Quality / Shared HTTP

**Date:** 2026-10-19  
**Orchestration:** orch-2026-10-19-17-06-strat003-io  
**Status:** ✅ Completed  
**Plan:** [2026-10-19-strat003-retry-quality-http.md](../plans/2026-10-19-strat003-retry-quality-http.md)  
**Follow-up:** [2026-10-19-god-object-decomposition-followup.md](../plans/2026-10-19-god-object-decomposition-followup.md)  
**ADR:** [2026-10-19-layering-and-ports.md](../architecture/2026-10-19-layering-and-ports.md)  
**Audit:** [2026-10-19-architecture-and-layout.md](../audits/2026-10-19-architecture-and-layout.md)  
**Parent:** orch-2026-10-19-15-06-godobj-p2

## Summary

Deepened God Object Phase 3–6: extracted the news/RSS strategy family into `app/strategies/`, wired a hybrid registry, applied `RetryPolicy` to OpenRouter/Pollinations and RSS GET, unified quality on the scheduled-post path via `QualityPipeline`, and started shared HTTP session injection for AI adapters. Verify gate: **smoke 2/2**; **unittest 193 OK (3 skipped)**.

## What Was Built

### Strategy extract + registry (STRAT-001…003)

- **STRAT-001:** Package `app/strategies/` + news-family ports (`NewsStrategyPorts`); no import of `bluesky_bot_v2`.
- **STRAT-002:** `QualityNewsStrategy` in `app/strategies/quality_news.py`; bot thin-delegates via `_build_news_strategy_ports()`; packaging syncs `strategies/` dir.
- **STRAT-003:** Hybrid registry — after `build_bound_registry`, overwrite `_create_quality_news_post` with extracted strategy instance; learning/A/B key stable; hermetic hybrid-overwrite test.

### RetryPolicy (RETRY-001…002)

- **RETRY-001:** Outbound I/O catalog; `OutboundRetryPolicies` / `build_outbound_retry_policies` at composition root; aliases on bot (`retry_ai`, `retry_rss_http`, …).
- **RETRY-002:** OpenRouter + Pollinations use `retry_policy.execute`; RSS path `_http_get_text_with_retry`; tests in `tests/test_retry_policy_retry002.py` (success-after-retry, budget/exhaust, CLIENT not retried). Budget/classify fixes applied so retries are bounded and classified correctly.

### Quality pipeline (QUAL-001…002)

- **QUAL-001:** `app/quality_pipeline.py` — single public facade; stages map gate → viral score.
- **QUAL-002:** `create_scheduled_post` uses `regenerate_until_quality` / `QualityPipeline.evaluate`; staged reasons; tests in `tests/test_quality_pipeline_qual002.py`.

### Shared HTTP (HTTP-001)

- OpenRouter + Pollinations receive injected/shared `ClientSession`; bot remains lifecycle owner.
- Leftovers: ad-hoc sessions in `bluesky_rich_posts.py` / `bluesky_post_formatter.py` → follow-up.

### Verification (VERIFY-001)

- Smoke: `python verify_bot.py --smoke` — **2/2 passed**
- Unittest: `python -m unittest discover -s tests -v` — **193 OK (3 skipped)**
- Follow-up plan updated: Phase 3 news extract done; Phase 4 AI+RSS; Phase 5 scheduled-post quality; Phase 6 partial

## Completed Tasks

1. ✅ **STRAT-001:** Strategy package skeleton + news-family ports (~17:08–17:12)
2. ✅ **STRAT-002:** Extract news/RSS into `QualityNewsStrategy`  
   - Files: `app/strategies/quality_news.py`, thin bot delegate, packaging
3. ✅ **STRAT-003:** Hybrid registry wire + packaging sync  
   - Files: `app/bluesky_bot_v2.py`, `app/post_strategies.py`, `tests/test_post_strategies_strat.py`, packaging scripts
4. ✅ **RETRY-001:** Catalog + inject `RetryPolicy` at composition root  
   - Files: `app/resilience_service.py`, bot wiring
5. ✅ **RETRY-002:** Wire AI adapters + RSS HTTP + tests  
   - Files: `app/openrouter_adapter.py`, `app/pollinations_adapter.py`, `tests/test_retry_policy_retry002.py`
6. ✅ **QUAL-001:** Design unified quality pipeline  
   - Files: `app/quality_pipeline.py`
7. ✅ **QUAL-002:** Migrate `create_scheduled_post` to unified quality  
   - Files: `app/quality_pipeline.py`, `app/bluesky_bot_v2.py`, `tests/test_quality_pipeline_qual002.py`
8. ✅ **HTTP-001:** Shared `ClientSession` injection for AI adapters
9. ✅ **VERIFY-001:** Smoke 2/2; unittest 193 OK (3 skipped); follow-up plan refreshed

## Technical Decisions

- **Hybrid registry:** Extracted `PostStrategy` for news; other keys remain bound methods until later family extracts.
- **Stable strategy name keys:** Registry name == config / learning / A/B string (`_create_quality_news_post`).
- **Retry at adapters:** `RetryPolicy.execute` wraps I/O; main loop stays thin; `ErrorClass.CLIENT` never retries.
- **Quality staging:** One facade; internal stages still use QualityGate + ContentQualityAnalyzer; callers see one API.
- **HTTP ownership:** Bot owns session create/recreate/close; adapters get injection.

## Metrics

| Metric | Value |
|--------|-------|
| Tasks | **9/9** completed |
| Smoke | **2/2** passed |
| Unittest | **193** OK, **3** skipped, **0** failed |
| Estimated effort | 12–16 h (plan) |
| Parent orch | orch-2026-10-19-15-06-godobj-p2 |

## Known Issues / Leftovers

- **Remaining strategy families** — opinion, tip, discussion, viral, … still on bot (`_create_*`).
- **Formatter / rich_posts sessions** — ad-hoc `ClientSession` not yet injected (Phase 6 partial).
- **ATProto / media upload RetryPolicy** — catalogued; wire deferred.
- **Phase 7** — further bot slices (state / schedule / learning façades).
- **Quality config namespace merge** — optional cleanup deferred.

## Related Documentation

- Plan: [2026-10-19-strat003-retry-quality-http.md](../plans/2026-10-19-strat003-retry-quality-http.md)
- Follow-up: [2026-10-19-god-object-decomposition-followup.md](../plans/2026-10-19-god-object-decomposition-followup.md)
- ADR: [2026-10-19-layering-and-ports.md](../architecture/2026-10-19-layering-and-ports.md)
- Audit: [2026-10-19-architecture-and-layout.md](../audits/2026-10-19-architecture-and-layout.md)
- Parent report: [2026-10-19-god-object-phase2-content-strategies-implementation.md](./2026-10-19-god-object-phase2-content-strategies-implementation.md)

## Next Steps

1. Extract remaining `_create_*` strategy families into `app/strategies/`.
2. Finish Phase 6: inject shared session into formatter / rich_posts.
3. Wire RetryPolicy on ATProto / media upload paths.
4. Optional re-audit for score delta after these drivers land.
