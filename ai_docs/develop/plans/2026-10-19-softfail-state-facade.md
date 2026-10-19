# Plan: Soft-Fail Helpers Extract + State Façade Slice

**Created:** 2026-10-19 18:33  
**Orchestration:** `orch-2026-10-19-18-33-softfail-state`  
**Parent / follow-up:** `ai_docs/develop/plans/2026-10-19-god-object-decomposition-followup.md`  
**Prior cycle:** `orch-2026-10-19-17-51-viral-p7` (viral + LEARN + CYCLE; soft-fail + state façade deferred)  
**ADR:** `ai_docs/develop/architecture/2026-10-19-layering-and-ports.md`  
**Status:** ⏳ Ready  
**Goal:** Extract soft-fail post helpers into `app/strategies/` (ports + hybrid registry); then one focused Phase 7 state façade slice for content dedup / publish marking beyond existing `state_service`.  
**Priority:** High  
**Total Tasks:** 8  
**Estimated Time:** ~8–12 hours  
**Mode:** docs (plans enabled)

---

## Constraints (hard)

| Rule | Detail |
|------|--------|
| Import graph | `strategies/` and any new state helpers must **NOT** import `bluesky_bot_v2` |
| Config / learning keys | Stable if registered: `_create_motivational_moment_post`, `_create_emergency_unique_post`; fallback chain resolve names unchanged |
| Pattern | `ImagePostHelper` + ports; hybrid registry `overwrite=True`; bot = composition root |
| Existing ports | Reuse / extend `FallbackPostPort`, `DuplicateContentPort`, `StructuredContentPort`, `ImagePostPorts` — do not reinvent |
| Packaging | New SoT modules in `packaging/sync-opt-from-sot.sh` + opt mirror |
| Verify | `python verify_bot.py --smoke` ; `python -m unittest discover -s tests -v` |
| Git | **No commits** in this orchestration |
| Scope | ≤10 tasks; one state façade slice only — defer heartbeat, engagement timeline, dry-run aggregation |

**Cut order if over budget:** drop STATE-001 first → keep soft-fail extract + PKG + VERIFY; note state slice in follow-up.

---

## Inventory (frozen at plan time)

### Soft-fail (SoT: `app/bluesky_bot_v2.py`)

| Method | ~Lines | Role | Call sites |
|--------|--------|------|------------|
| `_create_fallback_post_for_duplicate` | ~1239–1288 | Chains registry/`getattr` strategies; ends with emergency | `create_scheduled_post` duplicate path (~1512) |
| `_create_motivational_moment_post` | ~1290–1326 | Theme + structured AI + `ImagePostHelper` path | Fallback chain list; not a weighted `post_strategies` kind today |
| `_create_emergency_unique_post` | ~1328–1363 | Last-resort unique post | Fallback end; `CallableFallbackPost` as `emergency` (~671); other hard-fail (~3855) |

**Ports already present** (`app/strategies/ports.py`):
- `FallbackPostPort` / `CallableFallbackPost` — used for opinion soft-miss and `DynamicPostsPorts.emergency`
- Docs explicitly defer the three helpers above

**Deps for extract (expected):**
- `generate_structured_post_content` → `StructuredContentPort`
- `_create_post_with_image_generation` → `ImagePostHelper` + `ImagePostPorts`
- `_is_duplicate_content` → `DuplicateContentPort` (fallback chain uniqueness)
- Registry `resolve` / `StrategyLookupError` for fallback strategy names

### State façade remainder (beyond `state_service`)

`state_service.py` already owns: JSON memory save/load, ActionLedger, SessionStore, ActivityBudget, AtomicConfigWriter, SingleInstanceLock.

**Still direct on bot (candidates):**

| Cluster | Bot touchpoints | This cycle |
|---------|-----------------|------------|
| **Content dedup / publish sets** | `_generate_content_hash`, `_is_duplicate_content`, `_calculate_text_similarity`, `_mark_content_as_published`, `_cleanup_old_content_hashes` (+ retention trim on memory lists) | **STATE-001** (focused slice) |
| Heartbeat file I/O | `_update_heartbeat`, `_check_bot_hang` → `bot_heartbeat.txt` | Deferred |
| Session cache sync | commented/liked/reposted/followed caches ↔ `memory.*_cache` before save | Deferred (keep thin delegates / cycle runner) |
| Config load | `open` + `json.load` on config file | Deferred |
| Learning / outcomes writes | `topic_outcomes`, `content_performance`, `user_relationships` mutations | Deferred (LEARN already extracted weights) |

---

## Tasks Overview

1. **SOFT-001** — Inventory freeze + soft-fail ports surface  
2. **SOFT-002** — Extract motivational + emergency strategies  
3. **SOFT-003** — Extract fallback-for-duplicate helper  
4. **SOFT-004** — Hybrid registry wire + thin bot delegates  
5. **TEST-001** — Hermetic soft-fail tests  
6. **STATE-001** — Content dedup / publish façade slice  
7. **PKG-001** — Packaging sync + opt mirror  
8. **VERIFY-001** — Smoke + unittest + follow-up plan update  

---

## Progress (updated by orchestrator)

- ⏳ SOFT-001: Inventory + soft-fail ports
- ⏳ SOFT-002: Motivational + emergency extract
- ⏳ SOFT-003: Fallback-for-duplicate helper
- ⏳ SOFT-004: Registry wire + thin delegates
- ⏳ TEST-001: Soft-fail hermetic tests
- ⏳ STATE-001: Dedup/publish façade slice
- ⏳ PKG-001: Packaging sync
- ⏳ VERIFY-001: Verify gate + docs

---

## Dependencies Graph

```text
SOFT-001 → SOFT-002 → SOFT-003 → SOFT-004 → TEST-001 ─┐
STATE-001 (after SOFT-001 inventory; may parallel TEST) ┼→ PKG-001 → VERIFY-001
```

**Parallel after SOFT-004:** `TEST-001` ‖ `STATE-001` (STATE may reuse `DuplicateContentPort` adapter wired to new façade).

---

## Architecture Decisions

1. **Soft-fail module:** prefer `app/strategies/soft_fail_posts.py` (or `fallback_posts.py`) with:
   - `MotivationalMomentStrategy` / `EmergencyUniqueStrategy` implementing `PostStrategy`
   - Stable names: `MOTIVATIONAL_STRATEGY_NAME = "_create_motivational_moment_post"`, `EMERGENCY_STRATEGY_NAME = "_create_emergency_unique_post"`
2. **Fallback chain:** extract as a small helper/service (not necessarily a weighted `PostStrategy`) that takes registry resolve + `DuplicateContentPort` + emergency port — e.g. `DuplicateFallbackHelper` in the same module or `app/duplicate_fallback.py` under strategies package. Bot keeps thin async delegate.
3. **Reuse ports:** extend `ports.py` only if a new bundle is needed (`SoftFailPorts` = structured + image + duplicates); prefer composing existing Protocols.
4. **Registry:** hybrid overwrite for motivational + emergency when present in config **or** always register for `resolve()` used by fallback chain (parity with current `getattr` fallback). Do **not** invent new learning keys.
5. **State slice:** move dedup/publish-set logic into `state_service` (or thin `ContentPublishState` living next to it / in same module) with pure functions over memory fields; bot wires `CallableDuplicateContent` to façade. Heartbeat / cache sync → follow-up.
6. **Bot remains composition root** until methods shrink to delegates.

---

## Task Details

### SOFT-001: Inventory freeze + soft-fail ports surface
- **Priority:** Critical  
- **Complexity:** Simple  
- **Time:** ~45m  
- **Dependencies:** None  
- **Agent:** worker  
- **Files:** `app/strategies/ports.py` (docs / optional `SoftFailPorts` bundle), plan inventory (this section)

**Work:**
1. Confirm call sites and deps for the three soft-fail methods (table above).
2. Map each dep to an existing port or document a minimal new Protocol.
3. Freeze state-slice choice: **content dedup / publish** (not heartbeat).
4. Note any related soft-fail paths still on bot (e.g. news `fallback`, dynamic `emergency`) — wire those to extracted emergency strategy where already using `FallbackPostPort`.

**Acceptance:**
- [ ] Inventory tables match code
- [ ] Port gap list is empty or has ≤1 new Protocol
- [ ] STATE-001 scope locked to dedup/publish

---

### SOFT-002: Extract motivational + emergency strategies
- **Priority:** Critical  
- **Complexity:** Moderate  
- **Time:** ~2–3h  
- **Dependencies:** SOFT-001  
- **Agent:** worker  
- **Files:** `app/strategies/soft_fail_posts.py` (new), `app/strategies/__init__.py` (exports if needed), `app/strategies/ports.py`

**Work:**
1. Port `_create_motivational_moment_post` and `_create_emergency_unique_post` behind `PostStrategy` + `ImagePostHelper`.
2. Theme lists / prompts / timestamp fallbacks must preserve behavior (English prompts, content types `motivational` / `emergency`).
3. No import of `bluesky_bot_v2`.

**Acceptance:**
- [ ] Strategies construct from ports only
- [ ] Stable `STRATEGY_NAME` constants match old method names
- [ ] Bot methods can become thin wrappers in SOFT-004

---

### SOFT-003: Extract fallback-for-duplicate helper
- **Priority:** Critical  
- **Complexity:** Moderate  
- **Time:** ~1.5–2h  
- **Dependencies:** SOFT-002  
- **Agent:** worker  
- **Files:** same soft-fail module or `app/strategies/duplicate_fallback.py`

**Work:**
1. Extract `_create_fallback_post_for_duplicate` loop: resolve strategy → create → duplicate check → next; finally emergency.
2. Inject: registry-like resolve callable, strategy name list (same 5 keys + labels), `DuplicateContentPort`, emergency `FallbackPostPort`.
3. Keep logging semantics (info/warning messages) equivalent.

**Acceptance:**
- [ ] Helper has no bot import
- [ ] Strategy order and names identical to current list
- [ ] Emergency terminal path preserved

---

### SOFT-004: Hybrid registry wire + thin bot delegates
- **Priority:** Critical  
- **Complexity:** Moderate  
- **Time:** ~1–1.5h  
- **Dependencies:** SOFT-003  
- **Agent:** worker  
- **Files:** `app/bluesky_bot_v2.py` (`_build_post_strategy_registry`, composition, thin methods)

**Work:**
1. Build ports at composition root; instantiate strategies/helper.
2. `register(..., overwrite=True)` for motivational + emergency (and keep `DynamicPostsPorts.emergency` / news fallback pointing at same emergency callable/strategy).
3. Replace method bodies with thin delegates; keep method names for any residual `getattr` callers.

**Acceptance:**
- [ ] Hybrid registry overwrites stable keys
- [ ] Learning/config keys unchanged
- [ ] Soft-fail methods on bot are thin (≤~10 LOC each) or removed if unused

---

### TEST-001: Hermetic soft-fail tests
- **Priority:** High  
- **Complexity:** Moderate  
- **Time:** ~1.5–2h  
- **Dependencies:** SOFT-004  
- **Agent:** test-writer  
- **Files:** `tests/test_soft_fail_*.py` (new)

**Work:**
1. Unit tests with fakes: motivational / emergency produce posts via fake structured + image ports.
2. Fallback helper: first unique wins; all duplicate → emergency; resolve miss skips; exception continues.
3. Import-acyclic: strategies module must not import `bluesky_bot_v2`.

**Acceptance:**
- [ ] Hermetic tests pass without network/ATProto
- [ ] Acyclic import asserted
- [ ] Coverage of happy + duplicate exhaustion paths

---

### STATE-001: Content dedup / publish façade slice
- **Priority:** High  
- **Complexity:** Moderate  
- **Time:** ~2–3h  
- **Dependencies:** SOFT-001 (inventory lock); preferably after SOFT-004 so `CallableDuplicateContent` can bind façade  
- **Agent:** worker  
- **Files:** `app/state_service.py` and/or new thin helper colocated; `app/bluesky_bot_v2.py` (delegates); `tests/test_*dedup*` or extend existing

**Work:**
1. Move hash / similarity / is_duplicate / mark_published / cleanup-hash logic off bot into façade over memory fields (inject memory or operate on explicit sets/lists).
2. Bot methods become thin delegates; `DuplicateContentPort` wiring uses façade.
3. Hermetic tests for hash, Jaccard similarity threshold 0.8, URL hit, mark + prune caps (500→400).
4. **Out of scope:** heartbeat files, engagement cache sync, topic_outcomes mutations.

**Acceptance:**
- [ ] No duplicate algorithm left only on bot (bot may delegate)
- [ ] Behavior parity for scheduled-post dedup + soft-fail uniqueness checks
- [ ] Façade has no `bluesky_bot_v2` import
- [ ] Unit tests green

---

### PKG-001: Packaging sync + opt mirror
- **Priority:** High  
- **Complexity:** Simple  
- **Time:** ~30m  
- **Dependencies:** SOFT-004, STATE-001, TEST-001  
- **Agent:** worker  
- **Files:** `packaging/sync-opt-from-sot.sh`, `opt/bluesky-bot/` mirror

**Work:**
1. Ensure new modules listed / copied by sync script.
2. Run sync (or equivalent Windows-safe path used in prior cycles).
3. Confirm opt tree includes soft-fail + state changes.

**Acceptance:**
- [ ] SoT and opt mirror in sync for new/changed modules
- [ ] No parallel SoT invented under `opt/`

---

### VERIFY-001: Smoke + unittest + follow-up plan update
- **Priority:** Critical  
- **Complexity:** Simple  
- **Time:** ~45m  
- **Dependencies:** PKG-001  
- **Agent:** test-runner (+ documenter notes)  
- **Files:** follow-up plan status rows; optional report later by documenter

**Work:**
1. Run `python verify_bot.py --smoke`
2. Run `python -m unittest discover -s tests -v`
3. Update `2026-10-19-god-object-decomposition-followup.md`: soft-fail ✅; state façade partial (dedup done; heartbeat/cache deferred).
4. List remaining deferred items only (no new scope creep).

**Acceptance:**
- [ ] Smoke pass
- [ ] Unittest pass (skips OK if pre-existing)
- [ ] Follow-up plan reflects reality
- [ ] **No git commit**

---

## Implementation Notes

- Prefer one new strategies module over scattering soft-fail across theme/dynamic.
- `CallableFallbackPost(self._create_emergency_unique_post)` should bind the extracted strategy after wire (same object as registry).
- Fallback chain still resolves opinion / ai_insight / tip / discussion by **stable keys** already registered in prior orch cycles.
- Motivational may not appear in weighted `post_strategies` config — still register for `resolve()` parity.
- STATE-001 should not “boil the ocean”: if cleanup/retention already overlaps `StateService._apply_retention`, align rather than duplicate retention policy.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Fallback resolve order / getattr parity break | Golden list of 5 names + emergency; tests for skip-on-missing |
| Learning key rename | Forbidden — keep exact method-name strings |
| Dedup move changes similarity edge cases | Hermetic tests with known Jaccard fixtures |
| Scope creep into heartbeat / relationships | Explicit defer; cut STATE-001 if over budget |

---

## Deferred (follow-up only)

- Heartbeat file I/O → `state_service` / monitor helper  
- Engagement cache ↔ memory sync consolidation  
- Engagement timeline / smart engagement orchestration  
- Dry-run reporting aggregation  
- Any remaining soft-fail paths discovered outside the three named helpers (document in VERIFY, do not expand this orch)

---

## References

- Follow-up: `ai_docs/develop/plans/2026-10-19-god-object-decomposition-followup.md`  
- Prior plan: `ai_docs/develop/plans/2026-10-19-viral-strategies-phase7.md`  
- ADR-001: `ai_docs/develop/architecture/2026-10-19-layering-and-ports.md`  
- Ports: `app/strategies/ports.py` (`FallbackPostPort`, deferred soft-fail note)  
- Pattern: `app/strategies/viral_posts.py`, `app/strategies/image_post.py`  
- State SoT: `app/state_service.py`
