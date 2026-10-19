#!/usr/bin/env python3
"""Post-creation strategy package — ADR-001 / STRAT-001+.

Extracted strategy families live here (news/RSS first in STRAT-002).
The strategy *contract* remains ``post_strategies.PostStrategy``; this
package supplies ports/deps and concrete ``PostStrategy`` impls.

Import rules (ADR invariants):
- Must not import ``bluesky_bot_v2``.
- Prefer stdlib / typing / sibling ports; composition root wires adapters.
"""

from __future__ import annotations

__all__ = [
    "NewsStrategyPorts",
    "QualityNewsStrategy",
    "STRATEGY_NAME",
]

from .ports import NewsStrategyPorts
from .quality_news import STRATEGY_NAME, QualityNewsStrategy
