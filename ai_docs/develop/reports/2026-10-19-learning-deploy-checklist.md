# Deploy checklist — PolicyLearner / learning domains (PLRN-008)

**Date:** 2026-10-19  
**Scope:** post-deploy ops for strategy / format / engagement bandits

## Pre-deploy

- [ ] Package includes `policy_learner.py`, `engagement_learner.py`, `agent_decision_log.py` under `/opt/bluesky-bot/`
- [ ] `bot_config.json` has knobs: `learning_parameters`, `format_learning`, `engagement_learning`
- [ ] Hermetic smoke green: `python app/verify_bot.py --smoke` (or `python scripts/smoke_check.py`)

## On host (WorkingDirectory `/opt/bluesky-bot`)

- [ ] Process user can **write** state files (create if missing):
  - `learning_state.json` (strategy; or path from `learning_parameters.state_path`)
  - `learning_state_format.json` (`format_learning.state_path`)
  - `learning_state_engagement.json` (`engagement_learning.state_path`)
- [ ] Process user can write decision log (default `reports/agent_decisions.jsonl`)
- [ ] Restart service after deploy: `systemctl restart bluesky-bot`
- [ ] Confirm unit active: `systemctl status bluesky-bot`

## Journal / domains

- [ ] Watch picks/credits: `journalctl -u bluesky-bot -f` (or `-n 200`)
- [ ] Expect log lines mentioning domains: **strategy**, **format**, **engagement** (pick / credit / decision log)
- [ ] After a few cycles, state files should update mtime under WorkingDirectory

## Rollback note

If learning misbehaves: set `format_learning.enabled` / `engagement_learning.enabled` to `false` in `/etc/bluesky-bot/bot_config.json` (or disable via config reload path), restart; strategy bandit can keep running or freeze weights by not writing until `min_settled_posts`.
