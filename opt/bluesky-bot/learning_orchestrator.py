#!/usr/bin/env python3
"""Learning stack composition root (Wave 1–3).

Owns construction of PolicyLearner, FormatBandit, EngagementLearner,
FollowerTracker, LlmRetro, SafetyGovernor, and AgentDecisionLog.

Import rules:
- Must not import ``bluesky_bot_v2``.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from agent_decision_log import AgentDecisionLog
from engagement_learner import EngagementLearner
from follower_tracker import FollowerTracker
from llm_retro import LlmRetro
from policy_learner import FORMAT_ARM_KEYS, PolicyLearner
from safety_governor import SafetyGovernor, SafetyStatus

logger = logging.getLogger(__name__)


class LearningOrchestrator:
    """Holds learning-stack references; thin facades for safety + decision log."""

    def __init__(
        self,
        *,
        policy_learner: PolicyLearner,
        format_bandit: Optional[PolicyLearner],
        engagement_learner: EngagementLearner,
        follower_tracker: FollowerTracker,
        llm_retro: LlmRetro,
        safety_governor: SafetyGovernor,
        decision_log: AgentDecisionLog,
        config_path: str,
    ) -> None:
        self.policy_learner = policy_learner
        self.format_bandit = format_bandit
        self.engagement_learner = engagement_learner
        self.follower_tracker = follower_tracker
        self.llm_retro = llm_retro
        self.safety_governor = safety_governor
        self.decision_log = decision_log
        self.config_path = config_path

    @classmethod
    def from_config(
        cls,
        config: dict,
        *,
        config_path: str,
        decision_log_path: str | None = None,
    ) -> "LearningOrchestrator":
        """Build the full learning stack from bot config."""
        cfg = config or {}
        lp = cfg.get("learning_parameters", {}) or {}
        state_path = lp.get("state_path", "learning_state.json")
        arms = list(cfg.get("post_strategies", {}).keys())
        boot = dict(cfg.get("post_strategies", {}))

        policy_learner = PolicyLearner.load(
            path=state_path,
            params=lp,
            arm_keys=arms,
            bootstrap_weights=boot,
        )
        policy_learner.sync_arms_with_config(arms, boot)

        follower_tracker = FollowerTracker(
            path=lp.get("followers_state_path", "learning_followers.json")
        )

        fl = cfg.get("format_learning", {}) or {}
        if fl.get("enabled", True):
            fmt_params = {**lp, **fl}
            if "max_arm_share_24h" in fl:
                fmt_params["max_arm_share_24h"] = fl["max_arm_share_24h"]
            format_bandit: Optional[PolicyLearner] = PolicyLearner.load(
                path=fl.get("state_path", "learning_state_format.json"),
                params=fmt_params,
                arm_keys=list(FORMAT_ARM_KEYS),
                bootstrap_weights={"format_a": 0.5, "format_b": 0.5},
            )
        else:
            format_bandit = None

        engagement_learner = EngagementLearner.load(cfg, base_params=lp)

        log_path = (
            decision_log_path
            if decision_log_path is not None
            else lp.get("decision_log_path", "reports/agent_decisions.jsonl")
        )
        decision_log = AgentDecisionLog(
            path=log_path,
            max_lines=int(lp.get("decision_log_max_lines", 10000)),
        )

        retro_cfg = cfg.get("llm_retro", {}) or {}
        llm_retro = LlmRetro(
            state_path=retro_cfg.get("state_path", "learning_retro_state.json"),
            report_dir=retro_cfg.get("report_dir", "reports"),
            dry_run=bool(retro_cfg.get("dry_run", False)),
        )

        safety_governor = SafetyGovernor(cfg.get("safety_governor", {}))

        return cls(
            policy_learner=policy_learner,
            format_bandit=format_bandit,
            engagement_learner=engagement_learner,
            follower_tracker=follower_tracker,
            llm_retro=llm_retro,
            safety_governor=safety_governor,
            decision_log=decision_log,
            config_path=config_path,
        )

    def safety_status(
        self,
        budget_summary: dict | None,
        circuit_open: dict[str, bool] | None,
        followers_delta_1h: float | None,
        consecutive_errors: int = 0,
    ) -> SafetyStatus:
        """Delegate to :meth:`SafetyGovernor.evaluate`."""
        return self.safety_governor.evaluate(
            budget_summary=budget_summary,
            circuit_open=circuit_open,
            followers_delta_1h=followers_delta_1h,
            consecutive_errors=consecutive_errors,
        )

    def log_pick(
        self,
        domain: str,
        action: str,
        learner: Optional[PolicyLearner] = None,
        arm: Optional[str] = None,
        reason: Optional[str] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Write one AgentDecisionLog line from learner meta or explicit reason."""
        log = self.decision_log
        if log is None:
            return
        meta = getattr(learner, "last_pick_meta", None) if learner else None
        resolved_reason = reason
        if not resolved_reason and isinstance(meta, dict):
            resolved_reason = meta.get("reason")
        resolved_arm = arm
        if resolved_arm is None and isinstance(meta, dict):
            resolved_arm = meta.get("arm")
        try:
            log.log(
                domain=domain,
                action=action,
                arm=resolved_arm or "",
                reason=resolved_reason or "thompson_or_epsilon",
                context=dict(context or {}),
            )
        except Exception as exc:
            logger.warning("decision_log failed: %s", exc)
