# Plan: God Object Phase 2+ — ContentService Ports + Strategy Registry Wiring

**Created:** 2026-10-19 15:06  
**Orchestration:** orch-2026-10-19-15-06-godobj-p2  
**Status:** ✅ Completed (STRAT-003 deferred)  
**Priority:** High  
**Mode:** docs (Mode C)  
**Total Tasks:** 9 (8 completed, 1 deferred)  
**Estimated Time:** ~6–8 hours  
**Report:** [2026-10-19-god-object-phase2-content-strategies-implementation.md](../reports/2026-10-19-god-object-phase2-content-strategies-implementation.md)  

**Goal:** DIP for `ContentService` (ports, no `bot`) and start Phase 3 — full  
`PostStrategyRegistry` registration + switch `create_scheduled_post` dispatch;  
optional first strategy-family extract if budget allows.

**Parent completed:** `orch-2026-10-19-14-33-layout-godobj`  
**Source of truth (scope):** `ai_docs/develop/plans/2026-10-19-god-object-decomposition-followup.md`  
**ADR:** `ai_docs/develop/architecture/2026-10-19-layering-and-ports.md`

---

## Tasks Overview

1. **CONT-001** — Inventory `self.bot` in ContentService  
2. **CONT-002** — Define `content_ports.py` Protocols  
3. **CONT-003** — Refactor ContentService + composition-root wiring  
4. **CONT-004** — Hermetic ContentService port tests  
5. **PKG-001** — Packaging PYFILES + opt mirror sync  
6. **STRAT-001** — Register all `post_strategies` keys at composition root  
7. **STRAT-002** — Switch `create_scheduled_post` to registry dispatch  
8. **STRAT-003** — (Optional) Extract one strategy family to `app/strategies/`  
9. **TEST-001** — Registry + verify gate (unittest + smoke)

---

## Dependencies Graph

```text
CONT-001 → CONT-002 → CONT-003 → CONT-004
                         ↓
                      PKG-001
                         ↓
STRAT-001 → STRAT-002 → STRAT-003 (optional, may defer)
                ↓
             TEST-001  (also depends on CONT-004, PKG-001)
```

**Critical path:** CONT-001 → … → CONT-003 → STRAT-001 → STRAT-002 → TEST-001  
**Parallel after CONT-003:** PKG-001 can run alongside STRAT-001 if ports module already listed.

---

## Progress (updated by orchestrator)

- ✅ CONT-001: Inventory ContentService bot deps (Completed 2026-10-19)
- ✅ CONT-002: content_ports Protocols (Completed 2026-10-19)
- ✅ CONT-003: Refactor ContentService + wire (Completed 2026-10-19)
- ✅ CONT-004: Hermetic ContentService tests (Completed 2026-10-19 — `tests/test_content_ports_cont004.py`; registry slice `tests/test_post_strategies_strat.py`)
- ✅ PKG-001: Packaging sync (Completed 2026-10-19 — `content_ports.py` in PYFILES; `post_strategies.py` already listed; opt sync OK)
- ✅ STRAT-001: Full registry registration (Completed — all `post_strategies` config keys via `build_bound_registry`)
- ✅ STRAT-002: Dispatch via registry (Completed — `weighted_entries` / `resolve` in create_scheduled_post + duplicate fallback)
- ⏸️ STRAT-003: Optional strategy family extract (Deferred — budget; leave extraction for follow-up Phase 3)
- ✅ TEST-001: Registry tests + verify gate (Completed 2026-10-19 — smoke 2/2; unittest 153 ran, 3 skipped, OK)

---

## Architecture Decisions

- **DIP:** `ContentService` must not take `bot`; inject narrow Protocols (mirror Engagement Phase 1).
- **Known bot surface (pre-inventory hint):** only three touchpoints today —
  `_current_ab_suffix`, `_quality_gate_regen_mode`, `_spawn_background` + `delayed_performance_check`.
  CONT-001 must confirm via grep before freezing Protocols.
- **Composition root:** `AutonomousBlueskyBotV2` builds ports / registry; services stay free of bot type.
- **Import invariant:** `app/content_ports.py`, `content_service.py`, `post_strategies.py`,  
  `app/strategies/*` must **not** import `bluesky_bot_v2`.
- **Phase 3 interim:** registering bound methods (`getattr(self, name)`) is OK; extraction to  
  `PostStrategy` classes is incremental (STRAT-003 optional this cycle).
- **Stable strategy names:** config keys (`_create_*`) remain learning / A/B weight keys.

---

## Task Details

### CONT-001: Inventory `self.bot` in ContentService
- **Priority:** Critical  
- **Complexity:** Simple  
- **Time:** ~20 min  
- **Dependencies:** None  
- **Files:** `app/content_service.py` (read), optionally short note in plan progress  
- **Actions:**
  1. Grep / AST all `self.bot` / `getattr(self.bot` usages
  2. Map each to a candidate port responsibility
  3. Confirm no hidden dynamic access
- **Acceptance:**
  - Written inventory (table in worker notes / plan update): attribute → purpose → proposed port
  - No refactor yet
- **Status:** ✅ Completed 2026-10-19
- **Notes (inventory):**

  Scope: `app/content_service.py` only. Module-level helpers
  (`split_graphemes`, `sanitize_outbound_text`, `truncate_to_graphemes`,
  `validate_outbound_text`, `prepare_outbound_text`) have **no** bot access.
  AST + grep: no `getattr(self, "bot")`, no `vars(self.bot)`, no other dynamic
  bot attribute names beyond the three below. Pre-inventory hint confirmed.

  | # | Attribute / access | Method | Purpose | Suggested port |
  |---|--------------------|--------|---------|----------------|
  | 0 | `self.bot` (ctor store) | `__init__` | Hold god-object reference | Drop; inject ports instead |
  | 1 | `_current_ab_suffix` via `getattr(..., '')` | `build_structured_prompt` | Optional A/B prompt suffix appended to structured prompts | `PromptContextPort.ab_suffix` (str property) |
  | 2 | `_quality_gate_regen_mode` via `getattr(..., False)` | `build_structured_prompt` | When True, append “regen / less generic” instructions | `PromptContextPort.quality_gate_regen_mode` (bool property) |
  | 3a | `_spawn_background` (direct call) | `schedule_post_performance_checks` | Fire-and-forget background task scheduling | `BackgroundSchedulerPort.spawn(coro)` |
  | 3b | `delayed_performance_check(uri, delay)` (coro factory) | `schedule_post_performance_checks` | Build delayed post-performance check coroutine (delays 3600/21600/86400) | `BackgroundSchedulerPort.delayed_performance_check(uri, delay)` (awaitable factory) |

  **Port grouping for CONT-002:** two Protocols — `PromptContextPort` (items 1–2)
  and `BackgroundSchedulerPort` (items 3a–3b); optional `ContentPorts` aggregate
  dataclass mirroring `EngagementPorts`.

### CONT-002: Define `content_ports.py` Protocols
- **Priority:** Critical  
- **Complexity:** Moderate  
- **Time:** ~45 min  
- **Dependencies:** CONT-001  
- **Files:** `app/content_ports.py` (new)  
- **Actions:**
  1. Add Protocols / small views for prompt context (AB suffix, quality-regen flag) and background scheduling
  2. Optional aggregate dataclass `ContentPorts` (mirror `EngagementPorts`)
  3. Stdlib / typing only — no bot, services, adapters imports
- **Acceptance:**
  - Module importable without `bluesky_bot_v2`
  - Protocols cover every CONT-001 item
- **Status:** ✅ Completed 2026-10-19
- **Notes:** Added `PromptContextPort` (+ `PromptContextView` / `LivePromptContext`),
  `BackgroundSchedulerPort`, and `ContentPorts` bundle. Stdlib/typing only.

### CONT-003: Refactor ContentService off bot; wire in composition root
- **Priority:** Critical  
- **Complexity:** Moderate  
- **Time:** ~1–1.5 h  
- **Dependencies:** CONT-002  
- **Status:** ✅ Completed 2026-10-19  
- **Files:** `app/content_service.py`, `app/bluesky_bot_v2.py`, `app/content_ports.py`  
- **Actions:**
  1. Change ctor to accept ports (not `bot`); drop `self.bot`
  2. Add `_build_content_ports()` (or inline wiring) next to `_build_engagement_ports`
  3. Replace `ContentService(self)` with ports injection
  4. Preserve `build_structured_prompt` / `schedule_post_performance_checks` / `prepare_outbound_text` behavior
- **Acceptance:**
  - [x] No `self.bot` in `content_service.py`
  - [x] Import graph acyclic
  - [x] Outbound text / URL behavior unchanged
- **Notes:** `ContentService(ContentPorts)`; `LivePromptContext` + `LiveBackgroundScheduler`;
  composition root `_build_content_ports()`; opt mirrors synced for touched modules.

### CONT-004: Hermetic ContentService port tests
- **Priority:** High  
- **Complexity:** Moderate  
- **Time:** ~1 h  
- **Dependencies:** CONT-003  
- **Files:** `tests/test_content_ports_cont004.py` (new; name may vary, style of `test_engagement_ports_ref002.py`)  
- **Actions:**
  1. Fake ports only — no network / bot import
  2. Cover prompt AB suffix + regen append; schedule_post_performance_checks calls; prepare_outbound_text
  3. AST/source check: ContentService has no `.bot` attribute use
- **Acceptance:**
  - `python -m unittest tests.test_content_ports_cont004` (or chosen module) passes
  - Mirrors Engagement TEST pattern

### PKG-001: Sync packaging PYFILES + opt mirror
- **Priority:** High  
- **Complexity:** Simple  
- **Time:** ~20 min  
- **Dependencies:** CONT-002 (module exists); ideally after CONT-003  
- **Status:** ✅ Completed 2026-10-19  
- **Files:** `packaging/build-deb.sh`, `packaging/sync-opt-from-sot.sh`, opt mirror via sync script  
- **Actions:**
  1. Add `content_ports.py` to both PYFILES lists (and `strategies/` modules if STRAT-003 lands)
  2. Run `bash packaging/sync-opt-from-sot.sh` (or Windows-equivalent path if needed)
  3. If STRAT-003 deferred: only `content_ports.py` this cycle
- **Acceptance:**
  - [x] PYFILES lists include every new SoT runtime module
  - [x] Sync completes without missing-module WARN for new files
- **Notes:** `content_ports.py` added to both PYFILES (alphabetically before `content_service.py`);
  `post_strategies.py` already present. Sync via Git Bash: 23 files, no WARN. STRAT-003 N/A.

### STRAT-001: Register all `post_strategies` config keys
- **Priority:** Critical  
- **Complexity:** Moderate  
- **Time:** ~45 min  
- **Dependencies:** None strictly (can start after Phase 1); prefer after CONT-003 to reduce merge noise  
- **Files:** `app/bluesky_bot_v2.py`, possibly `app/post_strategies.py` helpers  
- **Actions:**
  1. Replace `build_proof_registry` / proof-only set with registration of **all** keys from `self.config.get("post_strategies", {})`
  2. Use `register_bound_methods` or loop + `getattr` interim (ADR-allowed)
  3. Log missing attrs without silently empty registry when config keys lack methods
- **Acceptance:**
  - Registry length matches available bound methods for config keys
  - Proof-only subset no longer the sole registered set at runtime

### STRAT-002: Switch `create_scheduled_post` to registry dispatch
- **Priority:** Critical  
- **Complexity:** Moderate  
- **Time:** ~1 h  
- **Dependencies:** STRAT-001  
- **Status:** ✅ Completed 2026-10-19  
- **Files:** `app/bluesky_bot_v2.py` (`create_scheduled_post`), docs comment in `post_strategies.py`  
- **Actions:**
  1. Replace `hasattr` / `getattr` loop with `post_strategy_registry.weighted_entries(strategies_config, skip_missing=…)`
  2. Keep weighted choice, quality-gate regen, A/B / trend boosts — only change how callables are obtained
  3. Prefer `skip_missing=False` or explicit error path equivalent to today’s “no valid strategies” log
  4. Update module docstring: Phase 1 “still getattr” → wired
- **Acceptance:**
  - [x] No getattr-based strategy list build in `create_scheduled_post`
  - [x] Runtime weights / quality / duplicates behavior equivalent
  - [x] Learning still keyed by strategy **name strings**
- **Notes:** `weighted_entries(..., skip_missing=True)` + empty-list error log (matches prior hasattr skip). Duplicate fallback uses `resolve`; non-config names still getattr. Smoke PASS.

### STRAT-003: (Optional) Extract one strategy family to `app/strategies/`
- **Priority:** Medium (budget-gated)  
- **Complexity:** Complex  
- **Time:** ~1.5–2 h if done; else defer  
- **Dependencies:** STRAT-002  
- **Files:** `app/strategies/` (new package), extracted module(s), composition-root register of instance(s)  
- **Actions:**
  1. Pick one coherent family (e.g. quality-news / personal-opinion) with lowest coupling
  2. Implement `PostStrategy`; register instance instead of bound method for those keys
  3. Leave other strategies as bound methods
  4. If budget exhausted: mark task deferred, note in follow-up — **do not block TEST-001**
- **Acceptance (if done):**
  - At least one config key resolves to extracted module
  - No bot import from `app/strategies/`
  - PKG-001 updated for new modules
- **Acceptance (if deferred):**
  - Explicit note in plan progress + remaining work left in follow-up plan Phase 3
- **Status:** ⏸️ Deferred 2026-10-19 — optional this cycle; no `app/strategies/` extract. Remaining Phase 3 extraction stays in follow-up plan.

### TEST-001: Registry tests + verify gate
- **Priority:** Critical  
- **Complexity:** Moderate  
- **Time:** ~1 h  
- **Dependencies:** STRAT-002, CONT-004, PKG-001; STRAT-003 optional  
- **Files:** `tests/test_post_strategy_registry.py` (new or extend existing), verify scripts  
- **Actions:**
  1. Unit tests: `register` / `get` / missing → `StrategyLookupError` / `weighted_entries` (skip_missing True/False)
  2. Optional fake strategy integration-style await
  3. Run verify gate:
     ```bash
     python verify_bot.py --smoke
     python -m unittest discover -s tests -v
     ```
- **Acceptance:**
  - New registry tests green
  - Smoke + full unittest discovery green
  - No commit unless user asks later
- **Status:** ✅ Completed 2026-10-19
- **Notes:** `python verify_bot.py --smoke` → 2 passed; `python -m unittest discover -s tests -q` → Ran 153, OK (skipped=3).

---

## Out of Scope (this cycle)

| Phase | Item | Where it stays |
|-------|------|----------------|
| **4** | RetryPolicy on outbound I/O | Follow-up plan |
| **5** | Quality pipeline merge (`QualityGate` vs analyzer) | Follow-up plan |
| **6** | Shared HTTP `ClientSession` injection | Follow-up plan |
| **7** | Further bot slices (state / schedule / learning) | Follow-up backlog |
| — | Full extraction of **all** `_create_*` strategies | Next cycle(s) after STRAT-003 |

---

## Implementation Notes

### ContentService ports (suggested shapes — finalize in CONT-001/002)

```python
# Illustrative — adjust to inventory
class PromptContextPort(Protocol):
    @property
    def ab_suffix(self) -> str: ...
    @property
    def quality_gate_regen_mode(self) -> bool: ...

class BackgroundSchedulerPort(Protocol):
    def spawn(self, coro) -> None: ...
    def delayed_performance_check(self, uri: str, delay: int): ...  # awaitable factory
```

Wire from bot fields / thin facades at composition root (same pattern as `DryRunGate` / `LiveEngagementConfig`).

### Strategy registry target dispatch

```python
entries = self.post_strategy_registry.weighted_entries(
    self.config["post_strategies"],
    skip_missing=False,  # or True + empty-guard matching today
)
strategy_fn = self._weighted_choice(entries)
post = await strategy_fn()
```

### Verify gate (mandatory end of cycle)

```bash
python verify_bot.py --smoke
python -m unittest discover -s tests -v
```

Also re-sync packaging when new `app/*.py` SoT modules are added.

### Subagent hints

| Task | Suggested agent |
|------|-----------------|
| CONT-001…003, STRAT-001…003 | worker |
| CONT-004, TEST-001 tests | test-writer then test-runner |
| Architecture spot-check after CONT-003 / STRAT-002 | senior-reviewer (optional) |
| Final report | documenter |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Incomplete ContentService inventory | CONT-001 grep before freezing ports |
| Registry `skip_missing` changes empty-strategy behavior | Match today’s error/log semantics in STRAT-002 |
| Audience-memory boost uses `fn.__name__` | Ensure `resolve` / `_to_callable` preserves `__name__` = config key |
| STRAT-003 scope creep | Hard budget: one family or defer; TEST-001 not blocked |
| Packaging drift | PKG-001 before verify |

---

## References

- Follow-up: `ai_docs/develop/plans/2026-10-19-god-object-decomposition-followup.md`
- Prep / Phase 0–1: `ai_docs/develop/plans/2026-10-19-layout-and-god-object-prep.md`
- ADR-001: `ai_docs/develop/architecture/2026-10-19-layering-and-ports.md`
- Engagement pattern: `app/engagement_ports.py`, `tests/test_engagement_ports_ref002.py`
- Registry skeleton: `app/post_strategies.py`
