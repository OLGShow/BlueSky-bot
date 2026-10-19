# Report: Layout FIX (Stages 1–4) + God Object Structural Prep

**Date:** 2026-10-19  
**Orchestration:** orch-2026-10-19-14-33-layout-godobj  
**Status:** ✅ Completed  
**Plan:** [2026-10-19-layout-and-god-object-prep.md](../plans/2026-10-19-layout-and-god-object-prep.md)  
**Audit source:** [2026-10-19-architecture-and-layout.md](../audits/2026-10-19-architecture-and-layout.md)

## Summary

Closed repo layout hygiene Stages 1–4 and Phase 0–1 of God Object decomposition: ADR for layering/ports, EngagementService DIP via narrow Protocols, and a post-strategy registry skeleton. Full God Object split deferred to the follow-up plan. Verify gate: **smoke 2/2 OK**; **132 unittest OK, 3 skipped**.

## What Was Built

### Layout (LAY-001…004)

- **LAY-001:** Removed tracked root `__pycache__/` from git index; `.gitignore` already covers bytecode caches.
- **LAY-002:** Aligned `opt/bluesky-bot/env.example` with root SoT (template sync, no secrets).
- **LAY-003:** Single systemd unit SoT at `systemd/bluesky-bot.service`; `packaging/build-deb.sh` copies unit (`cp`) instead of heredoc; LF line endings.
- **LAY-004:** Added `opt/README.md` — tracked mirror (`app/` → `opt/bluesky-bot/`) vs local-only runtime (venv, logs); Stage 5B untrack explicitly out of scope.

### Architecture + refactor (ADR / REF)

- **ADR-001:** Accepted ADR — layering (orchestration → services → ports → adapters), «services must not take `bot`», Engagement ports, strategy registry direction, Phase 0–1 vs 2+ boundary.
- **REF-001:** New `app/engagement_ports.py` — `typing.Protocol` contracts (client, ledger, budget, dry-run, stats/sets, config view); importable without `bluesky_bot_v2`.
- **REF-002:** `EngagementService` injects ports (no `self.bot`); `AutonomousBlueskyBotV2` remains composition root; packaging sync updated (`sync-opt-from-sot.sh` / `build-deb.sh` + opt mirrors).
- **REF-003:** Skeleton `app/post_strategies.py` (`PostStrategy` Protocol + registry register/get/list); opt-in wiring; follow-up plan for Phase 2+.

### Verification (TEST-001)

- Smoke: `python verify_bot.py --smoke` — exit 0, 2/2 passed  
- Unittest: `python -m unittest discover -s tests -v` — **132 ran, 3 skipped, 0 failed** (includes engagement ports + post_strategies coverage)

## Completed Tasks

1. ✅ **LAY-001:** Remove tracked root `__pycache__/`
   - Files: root `__pycache__/` (untracked), `.gitignore` (verified)
   - Acceptance: no tracked `__pycache__` paths

2. ✅ **LAY-002:** Align `opt/bluesky-bot/env.example` with root SoT
   - Files: `opt/bluesky-bot/env.example` (aligned with root `env.example`)

3. ✅ **LAY-003:** Single systemd unit SoT + build-deb `cp` + LF
   - Files: `systemd/bluesky-bot.service`, `etc/systemd/system/bluesky-bot.service`, `packaging/build-deb.sh`

4. ✅ **LAY-004:** Add `opt/README.md` (mirror vs local runtime)
   - Files: `opt/README.md` (new)

5. ✅ **ADR-001:** ADR layering + ports + phased decomposition (~10 min)
   - Files: [ai_docs/develop/architecture/2026-10-19-layering-and-ports.md](../architecture/2026-10-19-layering-and-ports.md)

6. ✅ **REF-001:** Define engagement ports (Protocols) (~4 min)
   - Files: `app/engagement_ports.py`

7. ✅ **REF-002:** Refactor EngagementService onto ports (~4 min)
   - Files: `app/engagement_service.py`, `app/engagement_ports.py`, `app/bluesky_bot_v2.py`, `app/verify_bot.py`, packaging sync scripts, `opt/bluesky-bot/*` mirrors

8. ✅ **REF-003:** Strategy registry skeleton + follow-up plan (~6 min)
   - Files: `app/post_strategies.py`, `app/bluesky_bot_v2.py`, packaging sync, opt mirrors
   - Docs: [2026-10-19-god-object-decomposition-followup.md](../plans/2026-10-19-god-object-decomposition-followup.md)

9. ✅ **TEST-001:** Tests + smoke/unittest verification gate (~1 min)
   - Notes: Smoke 2/2 exit 0; unittest 132 OK, 3 skipped
   - Coverage: fake ports (budget exhausted, duplicate ledger), registry register/get

## Technical Decisions

- **Layout SoT:** `app/` + root `env.example` + `systemd/bluesky-bot.service`; `opt/` = tracked mirror + local runtime (documented; no Stage 5B).
- **DIP start = Engagement first** — highest `bot` coupling; ContentService deferred to Phase 2.
- **Composition root stays** — `AutonomousBlueskyBotV2` wires ports; God Object not deleted in Phase 1.
- **Protocols over ABC** — structural typing minimizes churn.
- **Strategy skeleton only** — full post-path migration → follow-up Phase 3.
- **Out of scope this cycle:** RetryPolicy full wiring, unified quality pipeline, shared ClientSession, Stage 5B.

## Metrics

| Metric | Value |
|--------|-------|
| Tasks | **9/9** completed |
| Estimated | ~10.25h |
| Smoke | 2/2 pass, exit 0 |
| Unittest | **132** ran, **3** skipped, **0** failed |
| New modules (SoT) | `engagement_ports.py`, `post_strategies.py` |
| ADR | Accepted (Phase 0) |
| Follow-up plan | Ready (Phase 2+) |

## Known Issues / Deferrals

No new issue files created this cycle. Deferred work lives in the follow-up plan:

- ContentService ports (still takes `bot`)
- Full post strategy extraction (registry is proof/opt-in)
- RetryPolicy on all outbound I/O
- Unified quality pipeline (`QualityGate` vs `ContentQualityAnalyzer`)
- Shared aiohttp `ClientSession` injection
- Further `bluesky_bot_v2.py` slices (state / schedule / learning)
- Stage 5B: untrack `opt/*.py` (explicitly not this cycle)

## Related Documentation

- Plan: [ai_docs/develop/plans/2026-10-19-layout-and-god-object-prep.md](../plans/2026-10-19-layout-and-god-object-prep.md)
- ADR: [ai_docs/develop/architecture/2026-10-19-layering-and-ports.md](../architecture/2026-10-19-layering-and-ports.md)
- Follow-up: [ai_docs/develop/plans/2026-10-19-god-object-decomposition-followup.md](../plans/2026-10-19-god-object-decomposition-followup.md)
- Audit: [ai_docs/develop/audits/2026-10-19-architecture-and-layout.md](../audits/2026-10-19-architecture-and-layout.md)
- Prior cycles: [backlog-followup](./2026-10-19-backlog-followup-implementation.md), [audit-remediation](./2026-10-19-audit-critical-high-remediation-implementation.md)

## Next Steps

1. Parent orchestrator: archive workspace `active/orch-2026-10-19-14-33-layout-godobj/` → `completed/` (documenter does not archive).
2. Commits only on explicit user request (not part of this cycle).
3. **Next orchestration:** execute Phase 2+ from [god-object-decomposition-followup.md](../plans/2026-10-19-god-object-decomposition-followup.md) — start with ContentService ports + begin full strategy migration (≤10 tasks), same verify gate.
