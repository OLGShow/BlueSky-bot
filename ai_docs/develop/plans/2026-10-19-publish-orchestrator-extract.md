# Plan: ScheduledPostPublisher extract (create_scheduled_post)

**Created:** 2026-10-19  
**Status:** Slice A done  
**Parent:** God Object shell — next lever after bot_cycle / smart_engagement  
**Goal:** Move the body of `create_scheduled_post` behind `PublishPorts` without changing publish / bandit / quality behavior.

## Scope (slice A)

1. `app/publish_ports.py` — pragmatic `PublishPorts` dataclass (callables / flags)
2. `app/publish_orchestrator.py` — `ScheduledPostPublisher.run()`; **no** import of `bluesky_bot_v2`
3. Bot composition root: `_build_publish_ports()` + thin `create_scheduled_post` → `await self.publish_orchestrator.run()`
4. Keep `_enforce_bluesky_text_limit` / `_apply_quality_result_to_post` on bot (wired as ports)
5. Hermetic tests + packaging PYFILES + opt sync

## Out of scope

- Moving text-limit / quality-result helpers into ContentService
- Further shrinking of bandit pick façades into LearningOrchestrator

## Acceptance

- [x] Orchestrator must not import `bluesky_bot_v2`
- [x] Bot delegates `create_scheduled_post` to publisher
- [x] Tests: budget block, safety block, happy dry_run (no network)
- [x] Packaging lists `publish_ports.py` / `publish_orchestrator.py`
