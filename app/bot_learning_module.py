#!/usr/bin/env python3
"""Deprecated stub — replaced by ``policy_learner.PolicyLearner`` (PLRN Wave 1).

Do not import. Kept only so old paths fail loudly instead of silently learning.
"""

from __future__ import annotations


class BotLearningModule:  # pragma: no cover - unwired
    """Removed from runtime. Use PolicyLearner."""

    def __init__(self, *args, **kwargs) -> None:
        raise RuntimeError(
            "BotLearningModule is removed; use policy_learner.PolicyLearner"
        )
