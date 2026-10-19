#!/usr/bin/env python3
"""
Unified Quality Pipeline (QUAL-001) — single entry for scheduled-post quality.

## Why this module exists

`create_scheduled_post` historically runs **two** independent quality systems:

| Piece | Module | Role today | Config namespace |
|-------|--------|------------|----------------|
| ``QualityGate.check`` | ``growth_engine`` | Pre-publish **regen loop**: too short / low signal / fluff / semantic dup vs recent posts | ``quality_gate_settings`` |
| ``ContentQualityAnalyzer`` + bot scoring | ``ai_improvements`` (+ ``_evaluate_post_quality``) | Post-gate **viral / combined / triggers** thresholds | ``viral_content_settings`` (+ ``min_combined_score`` in gate settings) |

Callers should use **one** public API here. Internal stages still wrap the existing
pieces so thresholds and reason codes stay stable. QUAL-002 migrates
``create_scheduled_post`` onto ``evaluate`` / ``regenerate_until_quality``.

## Public API

- ``QualityPipeline.check(text, context) -> (ok, reason)`` — preferred simple entry
- ``QualityPipeline.evaluate(text, context) -> QualityResult`` — staged details for regen / logging
- ``regenerate_until_quality`` — gate regen loop + one score pass (scheduled-post path)
- ``check_gate`` / ``check_score`` — stage-scoped helpers matching old call sites

## Mapping: old call sites → pipeline stages

| Old call site | Stage | Pipeline method |
|---------------|-------|-----------------|
| ``quality_gate.check(text, recent_texts)`` in regen ``while`` | ``gate`` | ``check_gate`` / ``evaluate`` / ``regenerate_until_quality`` |
| ``_evaluate_post_quality(post)`` after gate / on fallback | ``score`` | ``check_score`` / ``evaluate`` (``run_gate=False``) |
| Dual pass in ``create_scheduled_post`` | ``gate`` then ``score`` | ``regenerate_until_quality`` / ``evaluate`` |

## Reason codes (stable)

**Gate** (pass-through from ``QualityGate``): ``ok``, ``too_short``,
``low_signal(...)``, ``too_fluffy(...)``, ``semantic_dup(...)``.

**Score**: ``ok``, ``empty_text``, ``missing_hashtags``,
``low_viral(...)``, ``low_combined(...)``, ``low_triggers(...)``.

Full ``check`` returns the **first failing** stage reason, or ``ok``.

No imports from ``bluesky_bot_v2`` (layering / ADR).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from ai_improvements import ContentQualityAnalyzer
from growth_engine import QualityGate

logger = logging.getLogger(__name__)

RegenModeSetter = Callable[[bool], None]
PostFactory = Callable[[], Awaitable[Any]]

_EMOJI_RE = re.compile(
    r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF'
    r'\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002700-\U000027BF]'
)

STAGE_GATE = 'gate'
STAGE_SCORE = 'score'
STAGE_FULL = 'full'


@dataclass
class QualityContext:
    """Inputs for a quality check (no bot reference).

    ``recent_posts`` feeds the gate semantic-dup window.
    Score knobs (``None`` → pipeline / config defaults) mirror
    ``viral_content_settings`` + bot ``min_post_quality_score`` /
    ``require_hashtags``.
    """

    recent_posts: List[str] = field(default_factory=list)
    min_viral_score: Optional[float] = None
    min_combined_score: Optional[float] = None
    required_engagement_triggers: Optional[int] = None
    require_hashtags: Optional[bool] = None
    run_gate: bool = True
    run_score: bool = True


@dataclass
class QualityResult:
    """Staged quality outcome for logging and QUAL-002 regen wiring."""

    ok: bool
    reason: str
    stage: str
    gate_ok: Optional[bool] = None
    gate_reason: Optional[str] = None
    score_ok: Optional[bool] = None
    score_reason: Optional[str] = None
    viral_score: float = 0.0
    basic_score: float = 0.0
    combined_score: float = 0.0
    factors: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def as_tuple(self) -> Tuple[bool, str]:
        return self.ok, self.reason


class QualityPipeline:
    """Facade: QualityGate (regen heuristics) then ContentQualityAnalyzer scoring.

    Config namespaces stay separate initially (``quality_gate_settings``,
    ``viral_content_settings``). Optional later merge is out of scope for QUAL-001.
    """

    def __init__(
        self,
        config: Optional[dict] = None,
        *,
        gate: Optional[QualityGate] = None,
        analyzer: Optional[ContentQualityAnalyzer] = None,
        min_combined_score: float = 0.7,
        require_hashtags: bool = True,
    ):
        cfg = config if config is not None else {}
        self._config = cfg
        self.gate = gate if gate is not None else QualityGate(cfg)
        self.analyzer = analyzer if analyzer is not None else ContentQualityAnalyzer()
        self.min_combined_score = float(min_combined_score)
        self.require_hashtags = bool(require_hashtags)

        viral = cfg.get('viral_content_settings', {}) or {}
        self.default_min_viral_score = float(viral.get('min_viral_score', 0.4))
        self.default_required_triggers = int(
            viral.get('required_engagement_triggers', 2)
        )

    @classmethod
    def from_config(
        cls,
        config: dict,
        *,
        min_combined_score: Optional[float] = None,
        require_hashtags: bool = True,
    ) -> 'QualityPipeline':
        """Build pipeline; resolve ``min_combined_score`` from gate settings if omitted."""
        quality_cfg = (config or {}).get('quality_gate_settings', {}) or {}
        if min_combined_score is None:
            raw = quality_cfg.get('min_combined_score', 0.7)
            try:
                min_combined_score = max(0.4, min(float(raw), 0.95))
            except (TypeError, ValueError):
                min_combined_score = 0.7
        return cls(
            config=config,
            min_combined_score=min_combined_score,
            require_hashtags=require_hashtags,
        )

    @property
    def max_regen(self) -> int:
        """Expose gate regen budget for QUAL-002 loop parity."""
        return int(getattr(self.gate, 'max_regen', 2))

    def _merge_context(self, context: Optional[QualityContext]) -> QualityContext:
        """Resolve ``None`` score knobs from pipeline / config defaults."""
        base = context or QualityContext()
        return QualityContext(
            recent_posts=list(base.recent_posts),
            min_viral_score=(
                self.default_min_viral_score
                if base.min_viral_score is None
                else float(base.min_viral_score)
            ),
            min_combined_score=(
                self.min_combined_score
                if base.min_combined_score is None
                else float(base.min_combined_score)
            ),
            required_engagement_triggers=(
                self.default_required_triggers
                if base.required_engagement_triggers is None
                else int(base.required_engagement_triggers)
            ),
            require_hashtags=(
                self.require_hashtags
                if base.require_hashtags is None
                else bool(base.require_hashtags)
            ),
            run_gate=base.run_gate,
            run_score=base.run_score,
        )

    def check_gate(
        self, text: str, recent_posts: Optional[List[str]] = None
    ) -> Tuple[bool, str]:
        """Stage ``gate`` — wraps ``QualityGate.check`` (growth_engine)."""
        return self.gate.check(text or '', recent_posts or [])

    def check_score(
        self, text: str, context: Optional[QualityContext] = None
    ) -> Tuple[bool, str]:
        """Stage ``score`` — analyzer + thresholds (ai_improvements / bot parity)."""
        result = self._evaluate_score(text or '', self._merge_context(context))
        return result.ok, result.reason

    def check(
        self, text: str, context: Optional[QualityContext] = None
    ) -> Tuple[bool, str]:
        """Public entry: gate → score. Returns ``(ok, reason)``."""
        return self.evaluate(text, context).as_tuple()

    def evaluate(
        self, text: str, context: Optional[QualityContext] = None
    ) -> QualityResult:
        """Full staged evaluation (gate then score unless skipped in context)."""
        ctx = self._merge_context(context)
        text = text or ''

        gate_ok: Optional[bool] = None
        gate_reason: Optional[str] = None
        if ctx.run_gate:
            gate_ok, gate_reason = self.check_gate(text, ctx.recent_posts)
            if not gate_ok:
                return QualityResult(
                    ok=False,
                    reason=gate_reason or 'gate_failed',
                    stage=STAGE_GATE,
                    gate_ok=False,
                    gate_reason=gate_reason,
                )

        if not ctx.run_score:
            return QualityResult(
                ok=True,
                reason='ok',
                stage=STAGE_GATE if ctx.run_gate else STAGE_FULL,
                gate_ok=gate_ok if ctx.run_gate else None,
                gate_reason=gate_reason if ctx.run_gate else None,
            )

        score = self._evaluate_score(text, ctx)
        if not score.ok:
            return QualityResult(
                ok=False,
                reason=score.reason,
                stage=STAGE_SCORE,
                gate_ok=gate_ok,
                gate_reason=gate_reason,
                score_ok=False,
                score_reason=score.reason,
                viral_score=score.viral_score,
                basic_score=score.basic_score,
                combined_score=score.combined_score,
                factors=score.factors,
                recommendations=score.recommendations,
                details=score.details,
            )

        return QualityResult(
            ok=True,
            reason='ok',
            stage=STAGE_FULL,
            gate_ok=gate_ok if ctx.run_gate else True,
            gate_reason=gate_reason if ctx.run_gate else 'ok',
            score_ok=True,
            score_reason='ok',
            viral_score=score.viral_score,
            basic_score=score.basic_score,
            combined_score=score.combined_score,
            factors=score.factors,
            recommendations=score.recommendations,
            details=score.details,
        )

    def _evaluate_score(self, text: str, ctx: QualityContext) -> QualityResult:
        """Parity with ``BlueSkyBotV2._evaluate_post_quality`` scoring (no bot import)."""
        if not text or not text.strip():
            return QualityResult(
                ok=False, reason='empty_text', stage=STAGE_SCORE, score_ok=False,
                score_reason='empty_text',
            )

        analysis = self.analyzer.analyze_post_potential(text)
        viral_score = float(analysis.get('viral_score', 0.0))
        factors = list(analysis.get('factors') or [])
        recommendations = list(analysis.get('recommendations') or [])

        basic_score = 0.0
        text_length = len(text)
        if 150 <= text_length <= 280:
            basic_score += 0.3
        elif 80 <= text_length <= 150:
            basic_score += 0.2
        else:
            basic_score += 0.1

        if _EMOJI_RE.search(text):
            basic_score += 0.2

        hashtag_count = text.count('#')
        if hashtag_count > 0:
            basic_score += 0.2
        elif ctx.require_hashtags:
            return QualityResult(
                ok=False,
                reason='missing_hashtags',
                stage=STAGE_SCORE,
                score_ok=False,
                score_reason='missing_hashtags',
                viral_score=viral_score,
                basic_score=basic_score,
                factors=factors,
                recommendations=recommendations,
            )

        if '?' in text:
            basic_score += 0.3

        combined_score = (viral_score * 0.6) + (basic_score * 0.4)
        meets_viral = viral_score >= ctx.min_viral_score
        meets_combined = combined_score >= ctx.min_combined_score
        meets_triggers = len(factors) >= ctx.required_engagement_triggers

        details = {
            'meets_viral_threshold': meets_viral,
            'meets_basic_threshold': meets_combined,
            'has_enough_triggers': meets_triggers,
            'min_viral_score': ctx.min_viral_score,
            'min_combined_score': ctx.min_combined_score,
            'required_engagement_triggers': ctx.required_engagement_triggers,
        }

        if not meets_viral:
            reason = f'low_viral({viral_score:.2f}<{ctx.min_viral_score})'
        elif not meets_combined:
            reason = f'low_combined({combined_score:.2f}<{ctx.min_combined_score})'
        elif not meets_triggers:
            reason = (
                f'low_triggers({len(factors)}<{ctx.required_engagement_triggers})'
            )
        else:
            reason = 'ok'

        ok = reason == 'ok'
        return QualityResult(
            ok=ok,
            reason=reason,
            stage=STAGE_SCORE,
            score_ok=ok,
            score_reason=reason,
            viral_score=viral_score,
            basic_score=basic_score,
            combined_score=combined_score,
            factors=factors,
            recommendations=recommendations,
            details=details,
        )


def check(
    text: str,
    context: Optional[QualityContext] = None,
    *,
    pipeline: Optional[QualityPipeline] = None,
    config: Optional[dict] = None,
) -> Tuple[bool, str]:
    """Module-level convenience: ``check(text, context) -> (ok, reason)``."""
    pipe = pipeline
    if pipe is None:
        pipe = (
            QualityPipeline.from_config(config)
            if config is not None
            else QualityPipeline()
        )
    return pipe.check(text, context)


async def regenerate_until_quality(
    post: Any,
    *,
    regenerate: PostFactory,
    pipeline: QualityPipeline,
    recent_posts: Optional[List[str]] = None,
    set_regen_mode: Optional[RegenModeSetter] = None,
) -> Tuple[Any, QualityResult]:
    """Gate-fail regen loop, then one score pass (scheduled-post parity).

    - Gate failure → regenerate up to ``pipeline.max_regen`` (sets regen mode
      around each ``regenerate`` call). Exhaustion → ``(None, last_result)``.
    - Score failure after gate pass → **no** further regen; returns
      ``(post, failing_result)`` with ``stage=score``.
    - Full pass → ``(post, ok_result)`` with ``stage=full``.
    """
    recent = list(recent_posts or [])
    regen_count = 0
    max_regen = pipeline.max_regen
    last = QualityResult(ok=False, reason='no_post', stage=STAGE_GATE)

    while post is not None and getattr(post, 'text', None):
        last = pipeline.evaluate(
            post.text,
            QualityContext(recent_posts=recent),
        )
        if last.ok:
            return post, last

        if last.stage == STAGE_GATE:
            regen_count += 1
            logger.warning(
                "⚠️ Quality gate failed: %s (attempt %s/%s)",
                last.reason,
                regen_count,
                max_regen,
            )
            if regen_count > max_regen:
                return None, last
            if set_regen_mode is not None:
                set_regen_mode(True)
            try:
                post = await regenerate()
            finally:
                if set_regen_mode is not None:
                    set_regen_mode(False)
            continue

        # Score stage failed — preserve prior semantics (no score regen)
        logger.warning(
            "⚠️ Quality score failed (%s): %s",
            last.stage,
            last.reason,
        )
        return post, last

    return None, last
