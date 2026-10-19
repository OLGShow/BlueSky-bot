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
from engagement_learner import (
    EngagementLearner,
    eligible_engagement_catch_up_checks,
)
from follower_tracker import FollowerTracker
from llm_retro import LlmRetro
from policy_learner import (
    FORMAT_ARM_KEYS,
    PolicyLearner,
    eligible_catch_up_checks,
    eligible_format_catch_up_checks,
)
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

    def apply_post_credits(
        self,
        post: dict,
        strategy_checks: list[str],
        format_checks: list[str],
        *,
        can_credit: bool,
        can_sync_config: bool,
        followers_delta: float | None = None,
        config: dict | None = None,
    ) -> dict:
        """Credit strategy + format for given check_ids. Mutates post rewarded lists.

        Returns ``{strategy_credited, format_credited, synced}``.
        If not ``can_credit``: return zeros (caller may log).
        """
        empty = {"strategy_credited": 0, "format_credited": 0, "synced": False}
        if not can_credit:
            return empty
        if not isinstance(post, dict):
            return empty

        strategy_credited = 0
        format_credited = 0
        synced = False

        strategy_key = post.get("strategy_key")
        likes = post.get("likes")
        reposts = post.get("reposts")
        replies = post.get("replies")
        rewarded = post.setdefault("rewarded_checks", [])
        if not isinstance(rewarded, list):
            rewarded = []
            post["rewarded_checks"] = rewarded

        for check_id in strategy_checks or []:
            if check_id in rewarded:
                continue
            if not strategy_key:
                continue
            ok = self.policy_learner.credit(
                strategy_key,
                likes,
                reposts,
                replies,
                check_id,
                followers_delta=followers_delta,
            )
            if ok:
                rewarded.append(check_id)
                strategy_credited += 1
                logger.info(
                    "🧠 PolicyLearner credit %s arm=%s likes=%s "
                    "reposts=%s replies=%s",
                    check_id,
                    strategy_key,
                    likes,
                    reposts,
                    replies,
                )

        ab_fmt = post.get("ab_format")
        if self.format_bandit is not None and ab_fmt and format_checks:
            fmt_rewarded = post.setdefault("format_rewarded_checks", [])
            if not isinstance(fmt_rewarded, list):
                fmt_rewarded = []
                post["format_rewarded_checks"] = fmt_rewarded
            for check_id in format_checks:
                if check_id in fmt_rewarded:
                    continue
                ok = self.format_bandit.credit(
                    ab_fmt,
                    likes,
                    reposts,
                    replies,
                    check_id,
                )
                if ok:
                    fmt_rewarded.append(check_id)
                    format_credited += 1
                    logger.info(
                        "🧠 FormatBandit credit %s arm=%s likes=%s "
                        "reposts=%s replies=%s",
                        check_id,
                        ab_fmt,
                        likes,
                        reposts,
                        replies,
                    )

        if strategy_credited > 0:
            if can_sync_config and config is not None:
                self.policy_learner.sync_config_weights(self.config_path)
                config["post_strategies"] = self.policy_learner.export_weights()
                synced = True
            elif not can_sync_config:
                logger.info(
                    "🛡️ SafetyGovernor: config sync blocked"
                )
            self.policy_learner.save()

        if format_credited > 0 and self.format_bandit is not None:
            self.format_bandit.save()

        return {
            "strategy_credited": strategy_credited,
            "format_credited": format_credited,
            "synced": synced,
        }

    def credit_checks_for_post(
        self,
        post: dict,
        now,
        *,
        can_credit: bool,
        can_sync_config: bool,
        followers_delta: float | None = None,
        config: dict | None = None,
    ) -> dict:
        """Resolve eligible strategy+format checks, then :meth:`apply_post_credits`."""
        strategy_checks = eligible_catch_up_checks(post, now)
        format_checks = (
            eligible_format_catch_up_checks(post, now)
            if self.format_bandit is not None
            else []
        )
        if not strategy_checks and not format_checks:
            return {"strategy_credited": 0, "format_credited": 0, "synced": False}
        return self.apply_post_credits(
            post,
            strategy_checks,
            format_checks,
            can_credit=can_credit,
            can_sync_config=can_sync_config,
            followers_delta=followers_delta,
            config=config,
        )

    def apply_engagement_credits(
        self,
        action: dict,
        check_ids: list[str],
        likes,
        replies,
        reposts,
        *,
        can_credit: bool,
    ) -> int:
        """Credit engagement topic arms; mutate ``rewarded_checks``; save if any."""
        if not can_credit:
            return 0
        eng = self.engagement_learner
        if eng is None or not eng.enabled:
            return 0
        if not isinstance(action, dict):
            return 0

        topic = action.get("topic") or "_other"
        rewarded = action.setdefault("rewarded_checks", [])
        if not isinstance(rewarded, list):
            rewarded = []
            action["rewarded_checks"] = rewarded

        credited = 0
        for check_id in check_ids or []:
            if check_id in rewarded:
                continue
            ok = eng.credit(topic, likes, replies, reposts, check_id)
            if ok:
                rewarded.append(check_id)
                credited += 1
                logger.info(
                    "🧠 EngagementLearner credit %s topic=%s likes=%s "
                    "reposts=%s replies=%s",
                    check_id,
                    topic,
                    likes,
                    reposts,
                    replies,
                )

        if credited > 0:
            eng.save()
        return credited

    def credit_checks_for_action(
        self,
        action: dict,
        now,
        likes,
        replies,
        reposts,
        *,
        can_credit: bool,
    ) -> int:
        """Resolve eligible engagement checks, then :meth:`apply_engagement_credits`."""
        checks = eligible_engagement_catch_up_checks(action, now)
        if not checks:
            return 0
        return self.apply_engagement_credits(
            action,
            checks,
            likes,
            replies,
            reposts,
            can_credit=can_credit,
        )
