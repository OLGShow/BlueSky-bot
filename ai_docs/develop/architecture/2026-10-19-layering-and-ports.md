# ADR-001: Layering, Ports, and Phased God-Object Decomposition

**Date:** 2026-10-19  
**Status:** Accepted  
**Orchestration:** orch-2026-10-19-14-33-layout-godobj  
**Related:** `ai_docs/develop/audits/2026-10-19-architecture-and-layout.md`,  
plan `ai_docs/develop/plans/2026-10-19-layout-and-god-object-prep.md`

---

## Context

`AutonomousBlueskyBotV2` (`app/bluesky_bot_v2.py`, ~4k LOC) remains a God Object.
Peripheral helpers (`state_service`, `growth_engine`, `url_safety`, `http_session`)
are extracted, but application services still take the whole bot:

- `EngagementService(bot)` — likes / reposts / follows via `self.bot.*`
- `ContentService(bot)` — content helpers via `self.bot.*`

That blocks DIP, unit testing with fakes, and incremental shrinkage of the orchestrator.
Import graph is already acyclic (services do not import `bluesky_bot_v2`); the missing
piece is **narrow ports** instead of the bot façade.

**Source of truth layout (repo):** runtime Python SoT lives under `app/` and is synced
flat into `opt/bluesky-bot/` for packaging/systemd (see `app/README.md`,
`packaging/sync-opt-from-sot.sh`). New ports, services, and strategy modules belong in
`app/`; deploy mirrors follow sync — do not invent a parallel tree under `opt/` as SoT.

---

## Decision

### 1. Layering

Target dependency direction (top → bottom):

```text
┌─────────────────────────────────────────────────────────────┐
│  Orchestration                                              │
│  AutonomousBlueskyBotV2 — composition root, lifecycle,      │
│  scheduling loops, wiring of services                       │
├─────────────────────────────────────────────────────────────┤
│  Application services                                       │
│  EngagementService, ContentService, …                       │
│  Use-case logic only; no knowledge of bot class             │
├─────────────────────────────────────────────────────────────┤
│  Ports (Protocols / narrow dataclasses)                     │
│  Contracts for client, ledger, budget, dry-run, stats, …    │
├─────────────────────────────────────────────────────────────┤
│  Adapters                                                   │
│  ATProto / HTTP / LLM clients, ledger impls, dry-run log,   │
│  activity budget, session stats dict wrappers               │
└─────────────────────────────────────────────────────────────┘
```

**Rules:**

| Layer | May depend on | Must not |
|-------|---------------|----------|
| Orchestration | services, ports, adapters | — (composition root) |
| Application services | ports, domain helpers | `AutonomousBlueskyBotV2`, concrete adapters by type |
| Ports | stdlib / typing only | bot, services, adapters |
| Adapters | external I/O libs, port shapes | application services |

### 2. Rule: services must not take `bot`

- Constructors accept **only** narrow `typing.Protocol`s and/or small dataclasses.
- No `self.bot`; no `getattr(bot, …)` escape hatches for new code.
- Bot remains the **composition root**: it builds port implementations from its fields
  (or thin facades) and injects them into services.
- Prefer structural typing (`Protocol`) to minimize churn vs. ABC hierarchies.

### 3. Target ports — Engagement (this cycle)

Minimum ports for `EngagementService` (names illustrative; exact module path in REF-001):

| Port | Responsibility | Typical bot source today |
|------|----------------|--------------------------|
| **Client** | `like`, `repost`, `follow` (async) | `bot.bluesky_client` |
| **Ledger** | `contains(key)`, `record(key)` | `bot.action_ledger` |
| **Budget** | `can_spend(action)`, `spend(action)` | `bot.activity_budget` |
| **Dry-run** | flag + `log(action, **kwargs)` | `bot.dry_run`, `bot.dry_run_log` |
| **Stats / identity sets** | session counters + liked/reposted/followed sets (and related append lists) | `bot.session_stats`, `liked_posts`, `reposted_posts`, `followed_users`, `recent_repost_authors` |

Also inject **engagement config** (mode + whitelist) as a narrow view / dataclass —
not the full `bot.config` blob unless unavoidable.

Ports must be importable **without** importing `bluesky_bot_v2`.

**ContentService:** same DIP rule applies, but port extraction is **follow-up**
(not this cycle). Document intent only; do not refactor ContentService here.

### 4. Strategy registry (OCP) for post creation

Post creation today is a family of private methods on the bot (scheduled / media /
link preview, etc.), which violates Open/Closed for new post kinds.

**Decision:** introduce a **strategy registry**:

- `Protocol` (e.g. `PostStrategy`) with async `execute` / `create`
- Registry: `register` / `get` / `list`
- Bot (or a thin facade) looks up strategies by key instead of growing new private methods

**This cycle:** skeleton only (module + Protocol + registry + optional one thin/no-op
wrapper). Full migration of create paths → follow-up plan.

### 5. Migration phases

| Phase | Scope | When |
|-------|--------|------|
| **0** | This ADR (layering + ports + phased plan) | **This cycle** (ADR-001) |
| **1** | Engagement ports + wire `EngagementService`; strategy registry skeleton | **This cycle** (REF-001…003) |
| **2+** | ContentService ports; full post-strategy migration; further bot slices | Follow-up plan |

**This cycle = Phase 0 + Phase 1 only.** Everything else →  
`ai_docs/develop/plans/2026-10-19-god-object-decomposition-followup.md` (created in REF-003).

### 6. Explicitly out of scope now (future)

Mentioned for traceability; **do not implement in this orchestration**:

- Full **RetryPolicy** wiring on all outbound I/O
- **Unified quality pipeline** (`QualityGate` vs `ContentQualityAnalyzer`)
- **Shared HTTP / aiohttp `ClientSession`** injection across adapters
- Stage 5B (untrack `opt/*.py`), ContentService ports, full strategy migration

---

## Consequences

### Positive

- Services become unit-testable with fake ports (budget exhausted, duplicate ledger keys).
- Coupling surface shrinks: engagement no longer depends on undocumented bot attributes.
- New post kinds can register strategies without editing the God Object’s private method set (once Phase 2+ lands).
- Clear contract for REF-001/002/003 workers — no guessing layer boundaries.

### Negative / trade-offs

- Short-term glue in `AutonomousBlueskyBotV2` (composition root) increases slightly while
  ports are assembled.
- Protocol surface must stay honest: inventory `self.bot.` in EngagementService before
  freezing ports (REF-001).
- ContentService still takes `bot` until follow-up — dual styles coexist briefly.

### Invariants to preserve

- Acyclic imports: `ports` / `*_service` **must not** import `bluesky_bot_v2`.
- Public engagement behavior (like / repost / follow, dry-run, budget, ledger) stays
  equivalent under ports wiring.
- `app/` remains SoT; packaging continues to sync flat to `opt/`.

---

## Migration phases (implementation checklist)

### Phase 0 — ADR (this document) ✅ when ADR-001 complete

- [x] Accept layering + «no `bot` in services»
- [x] Name Engagement ports and ContentService follow-up
- [x] Name strategy registry direction and cycle boundary
- [x] List future out-of-scope items

### Phase 1 — This cycle (REF-*)

1. **REF-001:** Define Engagement `Protocol`s (+ optional thin facades) under `app/`.
2. **REF-002:** Refactor `EngagementService` to inject ports; bot wires them; drop `self.bot`.
3. **REF-003:** Strategy registry skeleton + follow-up plan file for Phase 2+.
4. **TEST-001:** Fake-port tests + smoke / unittest gate.

### Phase 2+ — Follow-up (not this cycle)

- ContentService ports and wiring
- Full post strategy migration (scheduled / media / link preview)
- RetryPolicy on outbound I/O
- Unified quality pipeline
- Shared `ClientSession` injection
- Further cuts of `bluesky_bot_v2.py` (state, scheduling, learning hooks)

---

## References

- Audit: `ai_docs/develop/audits/2026-10-19-architecture-and-layout.md`
- Plan: `ai_docs/develop/plans/2026-10-19-layout-and-god-object-prep.md`
- App SoT: `app/README.md`
- Architecture skill: `.cursor/skills/architecture-principles/SKILL.md` (SOLID, DIP, Strategy)
