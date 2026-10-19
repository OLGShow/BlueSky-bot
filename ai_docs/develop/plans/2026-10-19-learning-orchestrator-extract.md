# Plan: LearningOrchestrator extract (God Object next slice)

**Created:** 2026-10-19  
**Status:** Slice 2 done (catch-up/credit path via orchestrator; pick/retro still on bot)  
**Parent:** architecture re-score 8.0 — top lever #3  
**Goal:** Move Wave 1–3 learning composition off `AutonomousBlueskyBotV2.__init__` / credit paths into `app/learning_orchestrator.py` without changing bandit math.

## Scope

1. `LearningOrchestrator` owns: PolicyLearner, FormatBandit, EngagementLearner, FollowerTracker, LlmRetro, SafetyGovernor, AgentDecisionLog  
2. Bot calls thin facades: `orch.pick_strategy(...)`, `orch.credit_post(...)`, `orch.maybe_retro()`, `orch.safety_status(...)`  
3. Hermetic tests with fakes; no import of `bluesky_bot_v2` from orchestrator  
4. Packaging PYFILES + smoke update  

## Slices

| Slice | Status | Notes |
|-------|--------|-------|
| 1 Construction + safety/log facades | done | `from_config`, `safety_status`, `log_pick` |
| 2 Catch-up / delayed credit | done | `apply_post_credits`, `apply_engagement_credits`, `credit_checks_for_*`; bot delegates |
| 3 Pick / retro facades | pending | strategy/format/engagement pick + maybe_retro |

## Out of scope

- Extracting full `create_scheduled_post`  
- Health/media/auth thin-shell (separate lever)

## Acceptance

- [x] Bot `__init__` learning block ≤ ~20 lines of wire  
- [x] Catch-up / delayed credit go through orchestrator  
- [ ] Tests green; deploy-verify checklist after ship  
