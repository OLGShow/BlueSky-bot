# Architecture + Layout Audit — 2026-10-19

**Baseline agents:** [senior-reviewer](9fa9e143-7737-4b56-9353-ab7c205caa5d) + [repo-organizer](03dd8eae-1c7d-440b-a7dd-24cf3ea53d08)  
**Re-audit agents:** [senior-reviewer](8075bcbb-7df0-4650-ad8e-06f5b3dffe5e) + [repo-organizer](71a36f86-fc13-48ed-a1b4-bc56cb9972c4)  
**Scope:** code architecture (`app/`) + local file organization

| | Baseline (afternoon) | Re-audit (after Phase 1–2) |
|--|---------------------:|---------------------------:|
| **Code health** | Needs Improvement — **5.5/10** | Needs Improvement — **6.5/10** (**+1.0**) |
| **Layout health** | Good; residual hygiene | **Healthy** (Stages 1–4 closed) |

---

## Executive summary (re-audit)

| Lens | Verdict |
|------|---------|
| **Local files** | Hygiene Stages 1–4 **done**; only optional leftovers |
| **Code architecture** | DIP + registry **improved**; God Object / Retry / dual quality / multi-session **unchanged** |

**Bottom line:** layout is largely settled; code moved in the right direction (+1.0), but the next +1.0 needs STRAT-003 + resilience/HTTP/quality — not more folders.

---

## Code scores: before → after

| Area | Baseline | Now | Δ |
|------|:--------:|:---:|:-:|
| Structure | 5 | **7** | **+2** |
| Dependencies | 4 | **7** | **+3** |
| Scalability | 5 | **5** | 0 |
| Maintainability | 4 | **6** | **+2** |
| Testability | 5 | **7** | **+2** |
| **Overall** | **5.5** | **6.5** | **+1.0** |

### Improved
| Was | Now |
|-----|-----|
| `EngagementService(bot)` / `ContentService(bot)` | Ports; no `self.bot` |
| Strategies via hasattr only | Full registry + `weighted_entries` dispatch |
| No layering ADR | ADR-001 Accepted |
| Weak service unit tests | Hermetic ports/registry tests (~153 unittest) |
| Layout hygiene open | Stages 1–4 closed |

### Unchanged (still open)
| Issue | Sev |
|-------|-----|
| God Object `bluesky_bot_v2.py` (~4k+ LOC; `_create_*` still on bot) | Critical |
| `RetryPolicy` underused | High |
| Dual quality (`QualityGate` vs `ContentQualityAnalyzer`) | Medium |
| Multiple `ClientSession` owners | Medium |
| STRAT-003 strategy class extract | Medium (deferred) |

### Mild new notes
- More composition-root glue (`_build_*_ports` / registry) without shrinking God Object LOC
- Registry wraps bound methods → OCP incomplete until STRAT-003

### Next levers (priority)
1. STRAT-003 — extract strategy families off the bot  
2. Wire `RetryPolicy` on outbound I/O  
3. One quality pipeline  
4. Shared HTTP session injection  

### Delta note (2026-10-19 evening — `orch-2026-10-19-17-06-strat003-io`)

Expected next-score drivers from the re-audit **completed this cycle** (formal re-score TBD):

| Driver | Status after orch |
|--------|-------------------|
| STRAT-003 news-family extract + hybrid registry | ✅ Done (`QualityNewsStrategy`) |
| `RetryPolicy` on outbound I/O | ✅ AI (OpenRouter/Pollinations) + RSS GET; ATProto/media leftover |
| One quality pipeline | ✅ `QualityPipeline` on `create_scheduled_post` |
| Shared HTTP session injection | 🟡 AI adapters done; formatter/rich_posts leftover |

Remaining score pressure: God Object LOC, other `_create_*` families, formatter sessions, Phase 7 slices. Report: [2026-10-19-strat003-retry-quality-http-implementation.md](../reports/2026-10-19-strat003-retry-quality-http-implementation.md).

### Delta note (2026-10-19 evening — `orch-2026-10-19-17-34-strat-families`)

Phase 3–6 leftovers from the evening STRAT-003 cycle **closed** (formal re-score still TBD):

| Driver | Status after orch |
|--------|-------------------|
| Remaining strategy families (STRAT-004…008) | ✅ Dynamic / theme / poll / insight+prediction extracted; list-fallback newline must-fix fixed |
| `RetryPolicy` on ATProto / media | ✅ RETRY-003 — Phase 4 outbound retry complete for catalogued I/O |
| Shared HTTP formatter / rich_posts | ✅ HTTP-002 — Phase 6 complete |
| Viral + soft-fail helpers | ⬜ Deferred |
| Phase 7 (scheduler / learning / state) | ⬜ Deferred |

Verify: smoke **2/2**; unittest **246** OK (3 skipped). Report: [2026-10-19-strat-families-http-retry-implementation.md](../reports/2026-10-19-strat-families-http-retry-implementation.md).

---

## Layout: baseline hygiene → status

| Baseline item | Status |
|---------------|--------|
| Tracked root `__pycache__/` | **FIXED** |
| `opt/.../env.example` drift | **FIXED** |
| Triple systemd SoT + heredoc | **FIXED** (SoT=`systemd/`; build-deb `cp`; `etc/` intentional copy) |
| Local `opt/` ~223 MB venv/logs | **OPEN** (expected; documented in `opt/README.md`) |
| Triple `bot_config.json` | **OPEN** (identical; optional doc of SoT) |

**Layout health: Healthy.** No mandatory FIX stages left. Optional: document `bot_config` SoT; later decide untrack `opt/*.py`.

---

## Baseline snapshot (frozen — afternoon audit)

### Code architecture (then)
**Strengths:** `state_service`, `url_safety`, `http_session`, `growth_engine`; acyclic imports; `app/` SoT.

**Top issues then:** God Object; services take `bot`; RetryPolicy; dual quality; multi-session; strategies as private methods.

### Layout (then)
**Healthy:** `app/` SoT, ops docs, packaging.  
**Remaining:** `__pycache__`, env drift, systemd triple SoT, opt size, bot_config copies.
