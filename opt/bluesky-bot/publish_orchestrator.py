#!/usr/bin/env python3
"""Scheduled post publish orchestration — extract from create_scheduled_post.

Owns the body of one scheduled-publish attempt behind :class:`PublishPorts`.
The bot keeps text-limit / quality-result helpers and wires ports at the
composition root.

Import rules:
- Must not import ``bluesky_bot_v2``.
"""

from __future__ import annotations

import logging
from datetime import datetime
from content_service import OutboundContentError
from policy_learner import (
    FORMAT_ARM_KEYS,
    recent_format_keys_24h,
    recent_strategy_keys_24h,
)
from post_strategies import successful_post_bandit_fields
from publish_ports import PublishPorts
from quality_pipeline import (
    STAGE_GATE,
    STAGE_SCORE,
    regenerate_until_quality,
)

logger = logging.getLogger(__name__)


class ScheduledPostPublisher:
    """Runs one scheduled-post attempt via injected :class:`PublishPorts`."""

    def __init__(self, ports: PublishPorts) -> None:
        self.ports = ports

    async def run(self) -> None:
        """ИСПРАВЛЕННОЕ создание запланированного поста с контролем качества и динамическими весами"""
        p = self.ports
        try:
            # SafetyGovernor gate — pause publish on risk signals (PLRN-022)
            _sg = p.safety_status()
            if not _sg.can_publish:
                logger.info(
                    "🛡️ SafetyGovernor: publish blocked — %s",
                    ", ".join(_sg.reasons) or "unknown",
                )
                return

            # Budget gate — check before any generation work
            if not p.can_spend_post():
                logger.info("📊 Activity budget exhausted for posting — skipping cycle")
                return

            # Проверяем дневной лимит
            current_date = datetime.now().date()
            if current_date != p.get_last_post_date():
                p.set_daily_post_count(0)
                p.set_last_post_date(current_date)

            if p.get_daily_post_count() >= p.get_max_posts_per_day():
                logger.info(
                    f"📊 Достигнут дневной лимит постов ({p.get_max_posts_per_day()}). Пропускаем."
                )
                return

            # НИКОГДА НЕ СОЗДАЕМ THREAD АВТОМАТИЧЕСКИ
            logger.info("🎨 Создание качественного поста...")

            arm_keys = p.get_strategy_arm_keys()
            if not arm_keys:
                logger.error("❌ Не найдено ни одной валидной стратегии в конфигурации!")
                return

            successful_posts = list(p.get_successful_posts())

            # FormatBandit pick (fallback: ABEngine ε-greedy when disabled)
            if p.has_format_bandit():
                recent_formats = recent_format_keys_24h(successful_posts)
                ab_format = p.pick_format_bandit(
                    list(FORMAT_ARM_KEYS), recent_formats
                )
                p.record_format_pick(ab_format)
                p.log_pick(
                    domain="format",
                    action="pick_format",
                    arm=ab_format,
                    learner=p.get_format_bandit_learner(),
                    context={"recent_24h": len(recent_formats)},
                )
            else:
                ab_format = p.pick_ab_format()
                p.log_pick(
                    domain="format",
                    action="pick_format",
                    arm=ab_format,
                    reason="ab_engine",
                )
            p.set_current_ab_format(ab_format)
            ab_suffix = p.get_prompt_suffix(ab_format)
            p.set_current_ab_suffix(ab_suffix)
            logger.info(
                f"🔬 A/B формат: {ab_format} | suffix len={len(ab_suffix)}"
            )

            # Trend Radar: topic of the day (telemetry / prompts only; no weight boost)
            try:
                trend_texts = [post.get("text", "")[:200] for post in successful_posts[-50:]]
                trend_texts += list(p.get_trend_timeline_snippets())
                trend_texts += list(p.get_trend_rss_headlines())
                trend_topic = p.get_topic_of_day(trend_texts)
                if trend_topic:
                    logger.info(
                        f"📡 Trend Radar: тема дня = {trend_topic} (из {len(trend_texts)} текстов)"
                    )
            except Exception:
                pass

            # Thompson pick → record → resolve (PLRN-005)
            recent_keys = recent_strategy_keys_24h(successful_posts)
            strategy_key = p.pick_strategy(arm_keys, recent_keys)
            p.record_strategy_pick(strategy_key)
            p.set_current_strategy_key(strategy_key)
            p.log_pick(
                domain="strategy",
                action="pick_strategy",
                arm=strategy_key,
                learner=p.get_policy_learner(),
                context={"recent_24h": len(recent_keys)},
            )
            post = await p.resolve_strategy(strategy_key)

            # Unified quality pipeline (QUAL-002): gate regen + score, staged reasons
            recent_texts = [item.get("text", "") for item in successful_posts[-20:]]

            async def _regen_weighted_strategy():
                # Re-pick via PolicyLearner on quality regen (Phase A)
                regen_key = p.pick_strategy(arm_keys, recent_keys)
                p.record_strategy_pick(regen_key)
                p.set_current_strategy_key(regen_key)
                p.log_pick(
                    domain="strategy",
                    action="pick_strategy_regen",
                    arm=regen_key,
                    learner=p.get_policy_learner(),
                    context={"recent_24h": len(recent_keys)},
                )
                return await p.resolve_strategy(regen_key)

            post, quality_result = await regenerate_until_quality(
                post,
                regenerate=_regen_weighted_strategy,
                pipeline=p.quality_pipeline,
                recent_posts=recent_texts,
                set_regen_mode=lambda on: p.set_quality_gate_regen_mode(bool(on)),
            )
            if post and (
                quality_result.ok or quality_result.stage == STAGE_SCORE
            ):
                p.apply_quality_result(post, quality_result)
            if post and quality_result.ok:
                logger.info(
                    "✅ Quality pipeline passed (gate+score, stage=%s)",
                    quality_result.stage,
                )

            if post and quality_result.ok:
                # Проверяем на дубликаты еще раз перед публикацией
                url = getattr(post, "url", None) if hasattr(post, "url") else None
                image_url = (
                    getattr(post, "image_url", None)
                    if hasattr(post, "image_url")
                    else None
                )

                if p.is_duplicate(post.text, url, image_url):
                    logger.warning(
                        "🔄 Обнаружен дубликат перед публикацией. Создаем альтернативный контент..."
                    )
                    fallback_post = await p.create_fallback()
                    if fallback_post and p.evaluate_quality(fallback_post):
                        post = fallback_post
                        url = (
                            getattr(post, "url", None)
                            if hasattr(post, "url")
                            else None
                        )
                        image_url = (
                            getattr(post, "image_url", None)
                            if hasattr(post, "image_url")
                            else None
                        )
                        logger.info("✅ Создан альтернативный пост вместо дубликата")
                    else:
                        logger.warning(
                            "⚠️ Не удалось создать альтернативный пост. Пропускаем публикацию."
                        )
                        return

                # Публикуем (или dry-run) — outbound validation at publish boundary
                try:
                    post = p.enforce_text_limit(post)
                except OutboundContentError as e:
                    logger.warning(
                        f"⚠️ Контент отклонён на границе публикации: {e}"
                    )
                    return
                if p.dry_run:
                    p.dry_run_log(
                        "send_post",
                        text=post.text[:120],
                        format=p.get_dry_run_format_label(),
                    )
                    return

                created = await p.send_post(post)
                p.spend_post()

                p.record_ab_impression(ab_format)
                p.mark_published(post.text, url, image_url)

                p.bump_posts_created()
                new_count = p.get_daily_post_count() + 1
                p.set_daily_post_count(new_count)
                logger.info(
                    f"✅ Опубликован качественный пост #{new_count}: "
                    f"{post.text[:80].replace(chr(10), ' ')}..."
                )

                followers_at_publish = await p.refresh_followers_at_publish()

                content_hash = p.generate_content_hash(post.text, url, image_url)
                strategy_key = p.get_current_strategy_key() or strategy_key
                post_data = {
                    "text": post.text,
                    "uri": created.uri,
                    "created_at": datetime.now(),
                    "timestamp": datetime.now().isoformat(),
                    "type": getattr(post, "content_type", "general"),
                    "quality_score": getattr(post, "quality_score", 0.8),
                    "content_hash": content_hash,
                    "url": url,
                    "image_url": image_url,
                    "ab_format": ab_format,
                    "format_rewarded_checks": [],
                    "viral_score": getattr(post, "viral_score", 0.0),
                    "viral_factors": getattr(post, "viral_factors", []),
                    "predicted_engagement": 0,
                    "actual_engagement": 0,
                    **successful_post_bandit_fields(strategy_key),
                }
                if followers_at_publish is not None:
                    post_data["followers_at_publish"] = followers_at_publish

                p.append_successful_post(post_data)

                if getattr(post, "viral_score", 0.0) >= 0.6:
                    p.append_viral_post(
                        {
                            "uri": created.uri,
                            "text": post.text[:100],
                            "viral_score": getattr(post, "viral_score", 0.0),
                            "factors": getattr(post, "viral_factors", []),
                            "timestamp": datetime.now().isoformat(),
                            "content_type": getattr(post, "content_type", "general"),
                        }
                    )
                    logger.info(
                        f"🔥 Пост добавлен в список потенциально вирусных "
                        f"(score: {getattr(post, 'viral_score', 0.0):.2f})"
                    )

                p.schedule_checks(created.uri)

            else:
                stage = getattr(quality_result, "stage", None)
                reason = getattr(quality_result, "reason", "unknown")
                if stage == STAGE_GATE:
                    logger.warning(
                        "⚠️ Quality gate exhausted / failed (%s). Публикация отменена.",
                        reason,
                    )
                elif stage == STAGE_SCORE:
                    logger.warning(
                        "⚠️ Пост не прошёл финальную оценку вирусности/порогов "
                        "(%s). Публикация отменена.",
                        reason,
                    )
                else:
                    logger.warning(
                        "⚠️ Пост не прошёл quality pipeline (%s/%s). "
                        "Публикация отменена.",
                        stage,
                        reason,
                    )

        except Exception as e:
            logger.error(f"❌ Ошибка создания поста: {e}")
            p.bump_errors()
