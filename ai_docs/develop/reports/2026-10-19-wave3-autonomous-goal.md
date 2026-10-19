# Wave 3 — Goal reward, LLM retro, SafetyGovernor

**Date:** 2026-10-19  
**Status:** implemented (PLRN-020 / 021 / 022)

## What shipped

### PLRN-020 — Followers-delta reward
- `FollowerTracker` (`learning_followers.json`) snapshots own `followers_count`
- On publish: `followers_at_publish` stored on the post
- On 6h/24h credit: `delta = now - followers_at_publish` blended into `compute_reward`
- Knob: `learning_parameters.followers_reward_weight` (default **0.15**), `followers_scale`

### PLRN-021 — LLM retro (weekly)
- `LlmRetro` proposes allowlisted tweaks to `learning_parameters` only
- Wired after startup catch-up via `maybe_run_llm_retro()`
- `dry_run: true` → report only under `reports/retro_*.json`
- Apply uses `.bak` + `AtomicConfigWriter`

### PLRN-022 — SafetyGovernor
- Gates **publish / credit / sync / engagement** from:
  - Bluesky/AI circuit open
  - budget remaining ratio
  - followers shock (`|Δ|1h`)
  - consecutive errors
- Config block: `safety_governor`

## Ops

| File | Role |
|------|------|
| `learning_followers.json` | follower snapshots |
| `learning_retro_state.json` | last retro run |
| `reports/retro_*.json` | LLM suggestions |
| `learning_state*.json` | bandits (Wave 1+2) |

Deploy: sync new modules + `bot_config.json`, restart `bluesky-bot`.  
Smoke: `python app/verify_bot.py --smoke` (includes Wave3 hermetic check).

## Rollback
- Set `llm_retro.enabled=false`, `safety_governor.enabled=false`, `followers_reward_weight=0`
- Restart service
