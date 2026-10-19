# ADR-002: PolicyLearner Bandit Replaces Stub / LEARN-001

**Date:** 2026-10-19  
**Status:** Accepted  
**Orchestration:** orch-policy-learner (PLRN Wave 1+2)  
**Related:** plan `.cursor/plans/policylearner_bandit_upgrade_d78a9f5f.plan.md`,  
report [2026-10-19-autonomous-learning-agent.md](../reports/2026-10-19-autonomous-learning-agent.md),  
ADR-001 [2026-10-19-layering-and-ports.md](./2026-10-19-layering-and-ports.md)

---

## Context

Strategy weights had **three conflicting writers**:

1. Stub `BotLearningModule` — rarely ran (exit of `run_bot_cycle`), weak signal.
2. LEARN-001 (`strategy_learning.apply_*`) — mutated in-memory `post_strategies` from `topic_outcomes`, **did not persist** to disk.
3. Ad-hoc topic ×1.3 boost at publish — dual policy alongside any learned weights.

Format used a separate ε-greedy `ABEngine.pick_format`. Engagement used static thresholds only. Delayed 6h/24h credits were lost on restart (asyncio tasks cancelled). Posts lacked durable `strategy_key` for credit attribution.

## Decision

Replace stub + LEARN-001 apply path with a **single Beta–Thompson bandit** (`PolicyLearner`) as the sole writer of strategy weights (`sync_config_weights` → `post_strategies` via `.bak` + atomic write).

Reuse the same core for:

- **FormatBandit** — `PolicyLearner` instance over `format_a` / `format_b` (`format_learning` knobs; share cap default 0.70).
- **EngagementLearner** — façade over `PolicyLearner` with topic arms + `_other`; multipliers on relevance score, credit from liked-post metrics.

Isolate domains with separate state files. Persist picks to `AgentDecisionLog` (`reports/agent_decisions.jsonl`). Orchestration (catch-up, delayed checks, composition) stays on the bot; bandit modules **must not** import `bluesky_bot_v2` (ADR-001 isolation).

### Credit model

- Reward: `score = likes + 2*replies + 3*reposts`; `r = 1 - exp(-score / reward_scale)`.
- Dual-credit: 6h weight 0.35, 24h weight 0.65; idempotent via `rewarded_checks` (and format/engagement equivalents).
- Anti-convergence: share cap, novelty idle, ε-floor, cold-start freeze until `min_settled_posts`.

## Consequences

**Positive:**

- One clear policy for strategy weights; restart catch-up restores missed credits.
- Hermetic-testable pure modules; shared math across domains.
- Observability via `report()` / decision JSONL without secrets.

**Negative / trade-offs:**

- Three state files + decision log to backup and keep writable on host.
- Cold-start freeze delays config snapshot until enough credit mass.
- Wave 3 (followers reward, LLM-retro) still backlog — reward remains engagement-proxy, not growth goal.

## Implementation

| Piece | Location |
|-------|----------|
| Shared bandit | `app/policy_learner.py` — `PolicyLearner`, `compute_reward`, catch-up helpers |
| Engagement façade | `app/engagement_learner.py` — `EngagementLearner` |
| Decision log | `app/agent_decision_log.py` — `AgentDecisionLog` |
| Wire / catch-up | `app/bluesky_bot_v2.py` — `catch_up_pending_credits`, `catch_up_engagement_credits` |
| Config knobs | `learning_parameters`, `format_learning`, `engagement_learning` in `bot_config.json` |

**Related files:** `app/policy_learner.py`, `app/engagement_learner.py`, `app/agent_decision_log.py`, `app/growth_engine.py` (legacy `pick_format` fallback), `app/smart_engagement.py` (topic multiplier port), packaging sync / smoke in `app/verify_bot.py`.
