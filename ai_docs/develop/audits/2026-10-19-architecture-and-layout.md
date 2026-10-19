# Architecture + Layout Audit — 2026-10-19

**Agents:** [senior-reviewer](9fa9e143-7737-4b56-9353-ab7c205caa5d) + [repo-organizer](03dd8eae-1c7d-440b-a7dd-24cf3ea53d08)  
**Scope:** code architecture (`app/`) + local file organization  
**Code health:** Needs Improvement — **5.5/10**  
**Layout health:** Good after Stage 1–5 cleanup; residual hygiene remains

---

## Executive summary

| Lens | Verdict |
|------|---------|
| **Local files** | SoT in `app/`, ops in `docs/ops/`, packaging aligned — structure OK |
| **Code architecture** | Periphery extracted well; `AutonomousBlueskyBotV2` still God Object |

Next architectural work is **ports + use-case splits**, not more folder moves.

---

## Code architecture (senior-reviewer)

### Strengths
- Solid extractions: `state_service`, `url_safety`, `http_session`, `growth_engine`
- Acyclic import graph (services do not import `bluesky_bot_v2`)
- Deploy SoT (`app/` → flat `opt/`) is coherent

### Top issues
| Sev | Issue |
|-----|--------|
| Critical | God Object `app/bluesky_bot_v2.py` (~4k LOC, ~80 methods) |
| High | `EngagementService(bot)` / `ContentService(bot)` — no DIP/ports |
| High | `RetryPolicy` underused; breakers incomplete |
| Medium | Dual quality pipelines (`QualityGate` vs `ContentQualityAnalyzer`) |
| Medium | Multiple aiohttp `ClientSession` owners |
| Medium | Post strategies as private methods (OCP) |

### Priority recommendations
1. ADR: layering + «services must not take `bot`»
2. Inject ports into engagement/content
3. Strategy registry for posts
4. Wire `RetryPolicy` on all outbound I/O
5. One quality pipeline
6. Shared HTTP session injection into adapters
7. Domain unit tests (engagement, gate, strategies)

---

## Local file layout (repo-organizer) — AUDIT only

### Healthy
- `app/` SoT, root `verify_bot.py` shim, `docs/ops/`, sync scripts from `app/`
- Secrets/runtime ignored; `ai_docs` config-owned paths respected

### Remaining hygiene
| Item | Risk |
|------|------|
| Tracked root `__pycache__/` with stale `.pyc` | Low — remove from git |
| `opt/.../env.example` drift vs root | Low — sync |
| Triple systemd unit SoT (`systemd/` / `etc/` / build-deb heredoc) | Low–Med |
| Local `opt/` ~223 MB (venv+logs, mostly ignored) | Low — document |
| Three `bot_config.json` copies (currently identical) | Low — document SoT |

**Not recommended now:** untrack `opt/*.py` (Medium; separate decision).

### Proposed FIX stages (awaiting approval)
1. Remove committed `__pycache__/`
2. Align `opt` `env.example` with root
3. Single systemd unit SoT + `cp` in `build-deb.sh`
4. `opt/README.md` (mirror vs local runtime)
5. (optional later) untrack opt py
6. (optional) bot_config sync documentation

---

## Checklist scores (code)

| Area | Score |
|------|------:|
| Structure | 5/10 |
| Dependencies | 4/10 |
| Scalability | 5/10 |
| Maintainability | 4/10 |
| Testability | 5/10 |
