#!/usr/bin/env python3
"""
ContentService — extracted content helpers to decouple orchestration.
"""

class ContentService:
    def __init__(self, bot):
        self.bot = bot

    def build_structured_prompt(self, prompt: str) -> str:
        ab_suffix = getattr(self.bot, '_current_ab_suffix', '')
        if ab_suffix:
            prompt = prompt.rstrip() + ab_suffix
        if getattr(self.bot, '_quality_gate_regen_mode', False):
            prompt = prompt + (
                '\n\nIMPORTANT: The previous attempt was rejected for being too generic or repetitive. '
                'Make this post highly specific: include at least one concrete number, fact, or named example. '
                'Avoid clichés. Be original and distinct.'
            )
        return prompt

    def schedule_post_performance_checks(self, uri: str) -> None:
        for delay in (3600, 21600, 86400):
            self.bot._spawn_background(self.bot.delayed_performance_check(uri, delay))

