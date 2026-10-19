#!/usr/bin/env python3
"""Post-creation strategy package — ADR-001 / STRAT-001+.

Extracted strategy families live here (news/RSS, image/theme helpers,
dynamic, theme, poll, insight/prediction).
The strategy *contract* remains ``post_strategies.PostStrategy``; this
package supplies ports/deps and concrete ``PostStrategy`` impls.

Import rules (ADR invariants):
- Must not import ``bluesky_bot_v2``.
- Prefer stdlib / typing / sibling ports; composition root wires adapters.
"""

from __future__ import annotations

__all__ = [
    "AI_INSIGHT_STRATEGY_NAME",
    "DynamicPostsPorts",
    "ImagePostHelper",
    "ImagePostPorts",
    "LIST_STRATEGY_NAME",
    "NewsStrategyPorts",
    "PERSONAL_INSIGHT_STRATEGY_NAME",
    "PERSONAL_OPINION_STRATEGY_NAME",
    "POLL_STRATEGY_NAME",
    "PREDICTION_STRATEGY_NAME",
    "PersonalInsightStrategy",
    "PersonalOpinionStrategy",
    "PredictionStrategy",
    "QUALITY_DISCUSSION_STRATEGY_NAME",
    "QUALITY_TIP_STRATEGY_NAME",
    "QualityAiInsightStrategy",
    "QualityDiscussionStrategy",
    "QualityListStrategy",
    "QualityNewsStrategy",
    "QualityPollStrategy",
    "QualityTipStrategy",
    "STRATEGY_NAME",
    "ThemePostHelper",
    "ThemePostPorts",
]

from .dynamic_posts import (
    PERSONAL_OPINION_STRATEGY_NAME,
    QUALITY_DISCUSSION_STRATEGY_NAME,
    QUALITY_TIP_STRATEGY_NAME,
    PersonalOpinionStrategy,
    QualityDiscussionStrategy,
    QualityTipStrategy,
)
from .image_post import ImagePostHelper, ThemePostHelper
from .insight_posts import (
    PERSONAL_INSIGHT_STRATEGY_NAME,
    PREDICTION_STRATEGY_NAME,
    PersonalInsightStrategy,
    PredictionStrategy,
)
from .poll_post import (
    STRATEGY_NAME as POLL_STRATEGY_NAME,
    QualityPollStrategy,
)
from .ports import DynamicPostsPorts, ImagePostPorts, NewsStrategyPorts, ThemePostPorts
from .quality_news import STRATEGY_NAME, QualityNewsStrategy
from .theme_posts import (
    AI_INSIGHT_STRATEGY_NAME,
    LIST_STRATEGY_NAME,
    QualityAiInsightStrategy,
    QualityListStrategy,
)
