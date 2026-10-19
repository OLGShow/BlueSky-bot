# When to lift `llm_retro.dry_run`

**Status:** Policy (dry_run stays **true** until criteria met)  
**Date:** 2026-10-19

## Current
`bot_config.json` → `llm_retro.dry_run: true`  
LLM writes `reports/retro_*.json` only; does **not** mutate `learning_parameters`.

## Lift dry_run only when ALL are true

1. **≥ 2 weekly retro reports** on the live host with sensible allowlisted patches (no junk / empty / out-of-bounds after validate).
2. **≥ 14 days** of Wave 3 bandit credit (strategy 6h/24h) without SafetyGovernor freeze storms.
3. Manual review of last retro patch: operator agrees keys/values look safe.
4. Deploy-verify: after flipping to `false`, hashes match SoT↔`/opt`↔`/etc`, restart, confirm one retro cycle either applies or no-ops cleanly in journal.

## Rollback
Set `dry_run: true` again, sync both configs, restart (`deploy-verify` checklist).

## Do not lift if
- Retro keeps proposing extreme `epsilon` / share caps every week  
- Followers shock / credit blocks are frequent  
- Config drift between `/opt` and SoT reappears after apply  
