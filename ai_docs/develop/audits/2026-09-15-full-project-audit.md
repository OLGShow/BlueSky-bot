# Project Audit Report

**Date**: 2026-09-15
**Scope**: full project (BlueSky-bot)
**Audited by**: senior-reviewer + security-auditor + reviewer

---

## Executive Summary

**Overall Health Score**: 0.0/10

| Severity | Architecture | Security | Code Quality | Total |
|----------|-------------|----------|--------------|-------|
| Critical | 1           | 2        | 0            | **3** |
| High     | 4           | 4        | 3            | **11** |
| Medium   | 7           | 5        | 6            | **18** |
| Low      | 3           | 3        | 3            | **9** |

**Recommendation**: Address 3 critical issues before next release / any further deploy.

Score formula applied: start 10; Critical −2 each (max −6); High −0.5 each (max −3); Medium −0.1 each (max −1); floor 0, 1 decimal → `10 − 6 − 3 − 1 = 0.0/10`.

---

## Critical Issues (fix immediately)

### [A1] God-class / God-module: `AutonomousBlueskyBotV2`

- **Category**: Architecture
- **Location**: `bluesky_bot_v2.py` (~3746 lines, ~100 methods)
- **Impact**: Single module owns auth, HTTP, RSS, content generation (~12 strategies), engagement, follow, quality gates, learning, health/recovery, image upload, and the main loop. Violates SRP and layered architecture; changes in one concern risk regressions across unrelated paths; blocks testability and horizontal decomposition.
- **Fix**: Split into bounded contexts (auth/session, content pipeline, engagement, RSS ingest, quality, learning/state, ops/health). Extract orchestrator that only wires cycle steps. Use `/refactor bluesky_bot_v2.py` for structural decomposition.

### [S1] Secrets in public GitHub history

- **Category**: Security
- **Location**: Git history / `origin/main`; commit `8cfede2` contained `.env` with `BLUESKY_PASSWORD`, `BLUESKY_HANDLE`, `OPENAI_API_KEY`. Repo: https://github.com/OLGShow/BlueSky-bot
- **Impact**: Credentials and API keys are recoverable from public history. Immediate account takeover / API abuse risk.
- **Fix**: Rotate **all** exposed credentials (Bluesky app password, OpenAI/other keys). Purge secrets from git history (filter-repo / BFG) and force-protect main; ensure `.env` never recommitted. Use `/implement [fix]` for secret-handling and rotation runbooks.

### [S2] Docker `COPY . .` can bake secrets into images

- **Category**: Security
- **Location**: Dockerfile (`COPY . .`); `.dockerignore` only excludes root `.env` / `session.json`
- **Impact**: Paths such as `etc/bluesky-bot/.env`, `opt/bluesky-bot/.env`, `opt/bluesky-bot/session.json`, `bot_memory.json` enter build context and can be layered into images. Anyone with image access gets live secrets/session material.
- **Fix**: Expand `.dockerignore` for all env/session/memory trees; never copy `etc/` / `opt/` runtime trees into images; prefer build-arg-free runtime mounts/secrets. Rebuild and rotate any keys that may have been baked. Use `/implement [fix]` for Docker/secret hardening.

---

## High Priority Issues (fix soon)

### [A2] False decomposition / DIP violation

- **Category**: Architecture
- **Location**: `content_service.py`, `engagement_service.py`
- **Impact**: Services take the entire bot and call `bot.bluesky_client`, `bot.action_ledger`, etc. — facades over the God-object with upward dependencies. Hard to unit-test or swap implementations.
- **Fix**: Inject narrow interfaces (client, ledger, config) instead of the bot instance. Use `/refactor content_service.py` / `/refactor engagement_service.py`.

### [A3] Competing quality contours

- **Category**: Architecture
- **Location**: `growth_engine.py` (`QualityGate`) vs `ai_improvements.py` / `bluesky_bot_v2.py` (`ContentQualityAnalyzer` / `_evaluate_post_quality`) vs Jaccard vs n-gram similarity
- **Impact**: Divergent thresholds produce inconsistent accept/reject behavior and opaque product quality.
- **Fix**: Single quality pipeline with one threshold config; deprecate duplicate analyzers.

### [A4] Premature / dead resilience

- **Category**: Architecture
- **Location**: `resilience_service.py`; auth / Pollinations retry paths
- **Impact**: `RetryPolicy` unused; circuit breakers created but `allow_request` / `record_success` largely unused; parallel retry logic elsewhere — false sense of resilience.
- **Fix**: Wire breakers into HTTP paths or remove dead code; unify retry policy.

### [A5] Fragmented configuration

- **Category**: Architecture
- **Location**: `env.example` (`POST_INTERVAL_*`, `MAX_POSTS_PER_DAY`, `BLUESKY_COMPLIANT_MODE`, `NO_AUTO_*`); runtime `bot_config.json`; hardcoded compliance ~169–172 in `bluesky_bot_v2.py`; duplicates in `load_external_config`, `__init__`, `generate_improved_bot_config`
- **Impact**: Operators believe env flags control behavior; runtime ignores them — compliance and rate-limit drift, deploy misconfiguration.
- **Fix**: One config source of truth; read documented env vars or remove them from `env.example`.

### [S3] ATProto session JWTs plaintext unprotected

- **Category**: Security
- **Location**: `state_service.py` (`SessionStore` → `session.json`); live at `opt/bluesky-bot/session.json`
- **Impact**: Session tokens readable by any process/user with filesystem access; account session theft.
- **Fix**: Restrict permissions (`chmod 600`), encrypt at rest or use OS keyring; avoid packing sessions into images/exports.

### [S4] Unsafe pickle deserialization

- **Category**: Security
- **Location**: `state_service.py` `_migrate_pickle()` — `pickle.load` on `bot_memory.pkl`
- **Impact**: Malicious/swapped pickle → RCE (OWASP A08).
- **Fix**: Prefer JSON-only migration; if pickle needed, isolate one-shot migrate under strict ownership checks and delete pickle after.

### [S5] SSRF / unrestricted outbound

- **Category**: Security
- **Location**: `bluesky_bot_v2.py` (feed/image URLs); `bluesky_rich_posts.py` (`fetch_link_metadata`); `rss_source_manager.py` (`add_candidate`)
- **Impact**: No scheme/host allowlist, no RFC1918 block — bot can hit internal metadata endpoints or attacker-controlled hosts.
- **Fix**: HTTPS-only allowlist, block private/link-local ranges, size/time limits. Use `/implement [fix]`.

### [S6] Live production secrets in local export trees

- **Category**: Security
- **Location**: root `.env`, `etc/bluesky-bot/.env`, `opt/bluesky-bot/.env`; systemd `ReadWritePaths` includes `/etc/bluesky-bot`
- **Impact**: Secrets duplicated across trees increase leak surface (backups, Docker, git, exports).
- **Fix**: Single secrets location outside repo; scrub export trees; tighten systemd paths.

### [Q1] Copy-paste post strategy factories

- **Category**: Code Quality
- **Location**: `bluesky_bot_v2.py` — `_create_quality_ai_insight`, `_create_quality_list_post`, `_create_viral_hot_take`, etc. (8+ nearly identical)
- **Impact**: Bugfixes must be repeated; divergent behavior across strategies.
- **Fix**: Parameterized factory / strategy registry. Use `/refactor bluesky_bot_v2.py`.

### [Q2] Missing automated tests

- **Category**: Code Quality
- **Location**: No `tests/` directory; only `verify_bot.py` for peripheral modules
- **Impact**: No coverage for `create_scheduled_post`, quality gate, `fetch_external_content`, `smart_engagement`, strategies, `pollinations_adapter` — regressions land silently.
- **Fix**: Add `tests/` with unit tests for critical paths and quality/engagement gates.

### [Q3] Dead score histogram branch in `smart_engagement`

- **Category**: Code Quality
- **Location**: `bluesky_bot_v2.py` ~2256–2264
- **Impact**: Second `elif s < 0.3` unreachable; 0.3–0.4 bucket wrong — metrics lie.
- **Fix**: Correct bucket boundaries (`s < 0.3`, `0.3 <= s < 0.4`, …).

---

## Medium Priority Issues (plan for next sprint)

### Architecture

#### [A6] Dual RSS source of truth

- **Category**: Architecture
- **Location**: Hardcoded `rss_feeds` in `bluesky_bot_v2.py` vs `SEED_FEEDS` + state in `rss_source_manager.py` (overwrite only every 50 cycles)
- **Impact**: Feed set drift; unexpected sources or stale seeds.
- **Fix**: Single owner for feed list; bot reads only from manager/state.

#### [A7] Parallel HTTP stacks

- **Category**: Architecture
- **Location**: Bot `http_session` + `PollinationsAI` own `aiohttp` session
- **Impact**: No shared connector/timeout/breaker — inconsistent limits and harder ops.
- **Fix**: Shared session factory with timeout/breaker policy.

#### [A8] Kitchen-sink `growth_engine.py`

- **Category**: Architecture
- **Location**: `growth_engine.py` — `QualityGate`, `ABEngine`, `TrendRadar`, `RepostPolicyFilter`, daily report I/O, `DryRunAction`
- **Impact**: Hard to reason about and test; mixed concerns.
- **Fix**: Split modules by responsibility. Use `/refactor growth_engine.py`.

#### [A9] Hard `State` ↔ `BotMemory` coupling

- **Category**: Architecture
- **Location**: `state_service.py` hardcodes `BotMemory` fields; `BotMemory` ignores filename in save/load
- **Impact**: Fragile migrations; surprising persistence paths.
- **Fix**: Explicit schema + path arguments; versioned state format.

#### [A10] No Protocol/ABC on core boundaries

- **Category**: Architecture
- **Location**: AI provider, Bluesky client, state store, quality checker
- **Impact**: Concrete coupling; hard to mock/swap.
- **Fix**: Introduce Protocols/ABCs at boundaries.

#### [A11] Duplicate tree `opt/bluesky-bot/` mirrors root modules

- **Category**: Architecture
- **Location**: `opt/bluesky-bot/` vs repo root
- **Impact**: Drift and wrong-tree deploys.
- **Fix**: One source tree; deploy via install/copy from CI artifact.

#### [A12] Stateful single-process design

- **Category**: Architecture
- **Location**: In-memory caches, `SingleInstanceLock`, JSON/pickle on disk
- **Impact**: No horizontal scale; restart/lock contention.
- **Fix**: Document single-instance constraint; plan external state if scale needed.

### Security

#### [S7] Prompt / content injection via RSS

- **Category**: Security
- **Location**: RSS → AI prompts/posts after weak `clean_html`
- **Impact**: Malicious feed content can steer model output or post harmful text.
- **Fix**: Stronger sanitization, length caps, instruction fencing, allowlist of fields.

#### [S8] Content sent to unauthenticated Pollinations AI

- **Category**: Security
- **Location**: `text.pollinations.ai` / `image.pollinations.ai`
- **Impact**: Third-party retention/privacy risk for prompts and generated content.
- **Fix**: Document risk; prefer authenticated/provider-controlled APIs; minimize PII.

#### [S9] Unpinned dependencies

- **Category**: Security
- **Location**: `requirements.txt` (`package>=` only); no lockfile / Dependabot / CI audit
- **Impact**: Supply-chain drift and unreproducible builds.
- **Fix**: Pin versions + lockfile; add dependency audit in CI.

#### [S10] Incomplete log sanitization

- **Category**: Security
- **Location**: `log_sanitizer.py`; auth errors may leak `str(e)`; authenticate logs handle
- **Impact**: Credentials/handles may appear in logs.
- **Fix**: Sanitize all error paths; never log secrets/handles in clear.

#### [S11] Behavioural / graph user data plaintext

- **Category**: Security
- **Location**: `bot_memory.json` / `ActionLedger` (DIDs, URIs, relationships)
- **Impact**: Privacy exposure if files leak.
- **Fix**: Access controls; minimize retention; consider encryption at rest.

### Code Quality

#### [Q4] Duplicated similarity / retention / fallback logic

- **Category**: Code Quality
- **Location**: `bluesky_bot_v2.py`, `growth_engine.py`, `state_service.py`, `pollinations_adapter.py`, `dynamic_content_system.py`
- **Impact**: Inconsistent behavior and duplicated bugs.
- **Fix**: Shared utility module with single implementation.

#### [Q5] Very long functions

- **Category**: Code Quality
- **Location**: `create_scheduled_post` ~175, `smart_engagement` ~179, `run_bot_cycle` ~165, `fetch_external_content` ~131, etc.
- **Impact**: Hard to test and review.
- **Fix**: Extract step helpers; keep cycle as orchestration only.

#### [Q6] `EngagementService` boilerplate + dry-run inconsistency

- **Category**: Code Quality
- **Location**: `engagement_service.py` — like/repost/follow; dry-run follow does not update `followed_users`
- **Impact**: Dry-run state diverges from real runs; misleading simulations.
- **Fix**: Unify action paths; update dry-run state consistently.

#### [Q7] Broad `except Exception` + silent fail

- **Category**: Code Quality
- **Location**: `bluesky_bot_v2.py`, `state_service.py`; `UnboundLocalError` risk in `StateService.save`
- **Impact**: Hidden failures; possible crash on save path.
- **Fix**: Narrow exceptions; log and re-raise where needed; fix variable init in `save`.

#### [Q8] Dead code / unused imports

- **Category**: Code Quality
- **Location**: `_generate_fallback_content` unused; `PostTemplates`, `PostFactory`, `ImageData`, `LinkCard`, `defaultdict` unused; unused imports in `rss_source_manager.py`; unused `math` in `growth_engine.py`; `_last_ab_format` vs `_current_ab_format` mismatch
- **Impact**: Noise and latent bugs (wrong attribute names).
- **Fix**: Remove dead code; align AB format attribute names.

#### [Q9] Weak typing

- **Category**: Code Quality
- **Location**: `Dict[str, any]` (builtin `any`); `-> callable`; `url: str = None` without `Optional`; untyped bot params
- **Impact**: Type checkers miss real bugs.
- **Fix**: Use `Any`, `Callable`, `Optional[str]`; type service boundaries.

---

## Low Priority / Suggestions

### Architecture

#### [A13] Dead / unused AI helpers

- **Category**: Architecture
- **Location**: `ImprovedAIStrategy`, `generate_improved_bot_config` in `ai_improvements.py`
- **Impact**: Maintenance noise.
- **Fix**: Remove or wire into active path.

#### [A14] Wrong climate SEED taxonomy

- **Category**: Architecture
- **Location**: `rss_source_manager.py` — Guardian tech / Nature CS labeled climate
- **Impact**: Topic contamination in climate content.
- **Fix**: Correct feed→topic mapping.

#### [A15] No circular imports (positive)

- **Category**: Architecture
- **Location**: Target modules
- **Impact**: Positive note — keep acyclic graph when refactoring.
- **Fix**: Preserve import discipline during decomposition.

### Security

#### [S12] `bot_monitor.py` uses `sudo systemctl restart`

- **Category**: Security
- **Location**: `bot_monitor.py`
- **Impact**: Local privilege lever if process compromised.
- **Fix**: Dedicated restart unit / restricted sudoers / drop sudo if possible.

#### [S13] App password kept in `self.password` for process lifetime

- **Category**: Security
- **Location**: Bot instance fields
- **Impact**: Longer exposure window in memory dumps.
- **Fix**: Prefer session-only after auth; clear password field.

#### [S14] Compliance env flags unread

- **Category**: Security
- **Location**: `BLUESKY_COMPLIANT_MODE` / `NO_AUTO_*` hardcoded; no env kill-switch
- **Impact**: Cannot emergency-disable auto actions via env.
- **Fix**: Honor kill-switch env vars documented in `env.example`.

### Code Quality

#### [Q10] RU/EN mismatch in prompts/defaults

- **Category**: Code Quality
- **Location**: Prompts/defaults when `language='en'`
- **Impact**: Wrong-language posts for EN mode.
- **Fix**: Language-consistent prompt packs.

#### [Q11] Misleading Pollinations `MODELS` keys

- **Category**: Code Quality
- **Location**: Pollinations adapter — `creative` / `powerful` / `fast` all map to `openai`
- **Impact**: Operators think they select different models.
- **Fix**: Align keys with real backends or document aliases.

#### [Q12] Changelog-style comments / outdated stubs

- **Category**: Code Quality
- **Location**: Various; false ops log about pause without sleep; hardcoded 2025 in `ai_improvements`
- **Impact**: Misleading ops and stale docs in code.
- **Fix**: Clean comments; fix pause/sleep logging; update year constants.

---

## Priority Matrix

| ID  | Issue                                              | Severity | Effort | Priority |
|-----|----------------------------------------------------|----------|--------|----------|
| S1  | Secrets in public GitHub history                   | Critical | M      | P0       |
| S2  | Docker COPY bakes secrets                          | Critical | S      | P0       |
| A1  | God-class `AutonomousBlueskyBotV2`                 | Critical | L      | P0       |
| S3  | Session JWTs plaintext                             | High     | S      | P1       |
| S4  | Unsafe pickle deserialization                      | High     | S      | P1       |
| S5  | SSRF / unrestricted outbound                       | High     | M      | P1       |
| S6  | Live secrets in export trees                       | High     | S      | P1       |
| A2  | False decomposition / DIP                          | High     | L      | P1       |
| A3  | Competing quality contours                         | High     | M      | P1       |
| A4  | Dead resilience wiring                             | High     | M      | P1       |
| A5  | Fragmented config                                  | High     | M      | P1       |
| Q1  | Copy-paste strategy factories                      | High     | M      | P1       |
| Q2  | No tests directory                                 | High     | L      | P1       |
| Q3  | Dead score histogram branch                        | High     | S      | P1       |
| A6  | Dual RSS source of truth                           | Medium   | M      | P2       |
| A7  | Parallel HTTP stacks                               | Medium   | M      | P2       |
| A8  | Kitchen-sink `growth_engine.py`                    | Medium   | L      | P2       |
| A9  | State↔BotMemory coupling                            | Medium   | M      | P2       |
| A10 | No Protocol/ABC boundaries                         | Medium   | M      | P2       |
| A11 | Duplicate `opt/bluesky-bot/` tree                  | Medium   | M      | P2       |
| A12 | Stateful single-process                            | Medium   | L      | P2       |
| S7  | RSS prompt/content injection                       | Medium   | M      | P2       |
| S8  | Unauthenticated Pollinations                       | Medium   | M      | P2       |
| S9  | Unpinned deps                                      | Medium   | S      | P2       |
| S10 | Incomplete log sanitization                        | Medium   | S      | P2       |
| S11 | Graph user data plaintext                          | Medium   | M      | P2       |
| Q4  | Duplicated similarity/retention                    | Medium   | M      | P2       |
| Q5  | Very long functions                                | Medium   | M      | P2       |
| Q6  | Engagement dry-run inconsistency                   | Medium   | S      | P2       |
| Q7  | Broad except / silent fail                         | Medium   | M      | P2       |
| Q8  | Dead code / unused imports                         | Medium   | S      | P2       |
| Q9  | Weak typing                                        | Medium   | M      | P2       |
| A13 | Dead ImprovedAIStrategy helpers                    | Low      | S      | P3       |
| A14 | Wrong climate SEED taxonomy                        | Low      | S      | P3       |
| A15 | Preserve no circular imports                       | Low      | —      | P3       |
| S12 | sudo systemctl in monitor                          | Low      | S      | P3       |
| S13 | Password held for process lifetime                 | Low      | S      | P3       |
| S14 | Compliance env flags unread                        | Low      | S      | P3       |
| Q10 | RU/EN prompt mismatch                              | Low      | S      | P3       |
| Q11 | Misleading Pollinations MODELS                     | Low      | S      | P3       |
| Q12 | Outdated comments / stubs                          | Low      | S      | P3       |

Effort legend: **S** = small, **M** = medium, **L** = large.

---

## Next Steps

### Immediate (before any further deploy)

1. **[S1]** Rotate all credentials exposed in git history; purge history / lock down repo.
2. **[S2]** Fix `.dockerignore` / Docker copy paths; rebuild images; assume prior images compromised.
3. **[A1]** Start God-class decomposition plan (do not block P0 security on full refactor, but freeze new features into the monolith).

### This sprint

- **[S3][S4][S5][S6]** Session hardening, pickle removal, SSRF allowlists, scrub local secret trees.
- **[A5][S14]** Unify config + honor compliance/kill-switch env flags.
- **[Q2][Q3]** Seed `tests/` for critical paths; fix engagement histogram.
- **[Q1][A2]** Begin strategy factory + service DIP refactors.

### Next sprint

- **[A3][A4][A6][A7][A8]** Quality unification, resilience wiring, RSS single source, shared HTTP, split `growth_engine`.
- **[S7][S8][S9][S10][S11]** Content injection controls, provider privacy, pinned deps, log sanitization, memory access.
- **[Q4][Q5][Q6][Q7][Q8][Q9]** Deduplicate logic, shorten functions, dry-run consistency, exception hygiene, typing.

### Backlog

- **[A9][A10][A11][A12]** State schema, Protocols, remove duplicate deploy tree, scale story.
- **[A13][A14][A15][S12][S13][Q10][Q11][Q12]** Cleanup, taxonomy, privilege reduction, i18n, model aliases, comment hygiene.

**Tooling hints**: Use `/refactor [file]` for structural issues; use `/implement [fix]` for feature-level security fixes.
