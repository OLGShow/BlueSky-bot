# Report: Autonomous Learning Agent (Wave 1+2)

**Date:** 2026-10-19  
**Orchestration:** orch-policy-learner / PLRN-000…012  
**Status:** ✅ Completed (Wave 1+2)  
**Plan:** [policylearner_bandit_upgrade](../../../.cursor/plans/policylearner_bandit_upgrade_d78a9f5f.plan.md)  
**Deploy:** [2026-10-19-learning-deploy-checklist.md](./2026-10-19-learning-deploy-checklist.md)  
**ADR:** [ADR-002](../architecture/ADR-002-policy-learner-bandit.md)

## Summary

Бот принимает решения в трёх независимых доменах через Beta–Thompson bandit. Stub SEAL (`BotLearningModule`) и LEARN-001 apply weights заменены единым ядром `PolicyLearner`. Format и engagement — отдельные state-файлы; picks пишутся в append-only decision log.

## Three decision domains

| Domain | Question | Arms | Module / instance | State file |
|--------|----------|------|-------------------|------------|
| **A. Strategy** | Какой тип поста писать? | `post_strategies` keys (`strategy_key`) | `PolicyLearner` | `learning_state.json` |
| **B. Format** | A/B формат текста? | `format_a`, `format_b` | `PolicyLearner` as FormatBandit (`self.format_bandit`) | `learning_state_format.json` |
| **C. Engagement** | Какие темы усиливать при like? | `topic_groups` + `_other` | `EngagementLearner` → wraps `PolicyLearner` | `learning_state_engagement.json` |

Shared math (reward, dual-credit 6h/24h, Thompson + ε, share cap, novelty, soft decay) lives in `app/policy_learner.py`. Bandit modules must not import `bluesky_bot_v2`.

```text
metrics (own post / liked post)
    → credit(arm, likes, reposts, replies, check_id)
    → Beta(α, β) + learning_state_*.json
    → pick_arm / topic_multiplier
    → AgentDecisionLog (reports/agent_decisions.jsonl)
```

## Knobs (`bot_config.json`)

### `learning_parameters` (strategy; base for other domains)

| Key | Default | Role |
|-----|---------|------|
| `reward_scale` | 10 | `r = 1 - exp(-score / scale)`; score = likes + 2·replies + 3·reposts |
| `credit_weight_6h` / `credit_weight_24h` | 0.35 / 0.65 | Fractional dual-credit |
| `min_settled_posts` | 5 | Freeze `sync_config_weights` / learned `export_weights` until mass ≥ N |
| `max_arm_share_24h` | 0.40 | Diversity quota |
| `novelty_idle_days` / `novelty_bonus` | 14 / 0.15 | Idle nudge on Thompson sample |
| `epsilon` | 0.10 | Uniform explore among share-eligible arms |
| `decay_every_cycles` / `decay_rate` | 20 / 0.005 | Soft decay toward prior |
| `weight_min` | 0.05 | Floor on exported weights |
| `warm_start_strength` | 4 | Prior concentration from bootstrap |
| `deltas_max` | 20 | Ring buffer of credit deltas |
| `state_path` | `learning_state.json` | Strategy state |

### `format_learning`

- `enabled` (bool), `max_arm_share_24h` (0.70 for 2 arms), `epsilon` (0.15), `state_path` → `learning_state_format.json`

### `engagement_learning`

- `enabled`, `max_arm_share_24h`, `epsilon`, `state_path` → `learning_state_engagement.json`
- `action_credit_delays_hours`: `[6, 24]`

## Public API (accurate names)

### `app/policy_learner.py`

- Helpers: `compute_reward`, `recent_arm_keys_24h`, `recent_strategy_keys_24h`, `recent_format_keys_24h`, `eligible_catch_up_checks`, `eligible_format_catch_up_checks`
- Class `PolicyLearner`: `load`, `save`, `pick_arm`, `record_pick`, `credit`, `maybe_decay`, `export_weights`, `sync_arms_with_config`, `report`, `write_report`, `sync_config_weights`
- After pick: `last_pick_meta` → `{arm, reason}` with reason ∈ `thompson` | `epsilon` | `share_cap`

### `app/engagement_learner.py`

- Helpers: `topic_arm_keys`, `infer_topic`, `arm_mean`, `topic_multiplier_from_mean`, `append_engagement_action`, `eligible_engagement_catch_up_checks`, `build_like_action`
- Class `EngagementLearner`: `load`, `infer_topic`, `topic_multiplier`, `credit`, `record_action`, `sync_arms`, `save`, `maybe_decay`, `report`, `action_credit_delays_hours`
- Multiplier: `0.5 + mean` → range **[0.5, 1.5]**; `effective_score = relevance_score * mult`

### `app/agent_decision_log.py`

- `sanitize_context` (strips secret-like keys; truncates text)
- Class `AgentDecisionLog`: `log(domain, action, arm, reason, context)`, `recent(n)`
- Default path: `reports/agent_decisions.jsonl`; rotate keep last **10000** lines

## Ops

### Catch-up (restart-safe)

- Bot methods: `catch_up_pending_credits` (strategy + format), `catch_up_engagement_credits`
- Eligibility helpers return due check_ids for age ∈ ~[6h, 36h] windows when check not yet in `rewarded_checks` / `format_rewarded_checks` / action `rewarded_checks`
- Idempotency: credit once per `(entity, check_id)` via those lists on posts/actions

### State files (WorkingDirectory)

| File | Domain |
|------|--------|
| `learning_state.json` | Strategy |
| `learning_state_format.json` | Format |
| `learning_state_engagement.json` | Engagement |
| `reports/agent_decisions.jsonl` | Decision log |
| `reports/learning_report.json` | Optional `write_report` snapshot |
| `bot_config.json.bak` | Before `sync_config_weights` rewrite of `post_strategies` |

Strategy is the **only** writer of `post_strategies` weights (`PolicyLearner.sync_config_weights`). Format/engagement do not mutate strategy weights. `topic_outcomes` ×1.3 boost removed.

### Decision log line shape

```json
{"ts":"...","domain":"strategy|format|engagement","action":"...","arm":"...","reason":"thompson|epsilon|share_cap","context":{}}
```

No secrets/PII in context (`sanitize_context`).

## How to verify

1. Hermetic: `python -m pytest tests/test_policy_learner.py tests/test_engagement_learner.py tests/test_agent_decision_log.py` (plus format/policy data suites if present)
2. Smoke: `python app/verify_bot.py --smoke` — loads three bandit states in tmpdir, pick/credit each
3. Deploy ops: follow [2026-10-19-learning-deploy-checklist.md](./2026-10-19-learning-deploy-checklist.md) (writable state files, restart, journal domains)
4. Runtime: after cycles, state mtimes update; journal mentions strategy / format / engagement picks or credits

## What was removed / replaced

- `BotLearningModule.analyze_performance_and_learn` (exit-only stub)
- LEARN-001 `apply_strategy_weights_from_outcomes` / in-memory-only weight mutation
- Dual policy: topic ×1.3 boost on strategy pick
- `ABEngine.pick_format` as primary chooser (legacy fallback when `format_learning.enabled` is false)

## Wave 3 backlog (not in this report)

- Followers-delta reward, LLM-retro weekly, extra safety governor — see plan Wave 3.

## Related documentation

- Deploy checklist: [2026-10-19-learning-deploy-checklist.md](./2026-10-19-learning-deploy-checklist.md)
- ADR-002: [ADR-002-policy-learner-bandit.md](../architecture/ADR-002-policy-learner-bandit.md)
- ADR-001 (layering): [2026-10-19-layering-and-ports.md](../architecture/2026-10-19-layering-and-ports.md)
