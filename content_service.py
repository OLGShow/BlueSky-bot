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

        # Universal quality constraints for structured social posts.
        # Keeps prompts "human-like" and aligned with quality gate expectations.
        prompt = prompt.rstrip() + (
            "\n\nSTRICT OUTPUT CONTRACT:\n"
            "Return ONLY valid JSON object with exactly two keys: "
            "\"post_text\" and \"hashtags\".\n"
            "Do not use markdown, code fences, prefaces, or explanations.\n"
            "\"post_text\": natural human voice, specific and concrete, 170-240 characters, "
            "first-person perspective when appropriate, include at least one tangible detail "
            "(number, named tool, event, or example), and include one engagement hook "
            "(question, contrast, or prediction).\n"
            "\"hashtags\": 2-4 English hashtags, each starts with #, no punctuation-only tags.\n"
            "Avoid generic filler like 'this changes everything' without evidence."
        )

        if getattr(self.bot, '_quality_gate_regen_mode', False):
            prompt = prompt + (
                '\n\nIMPORTANT: The previous attempt was rejected for being too generic or repetitive. '
                'Make this post highly specific: include at least one concrete number, fact, or named example. '
                'Avoid clichés. Be original and distinct. '
                'Ensure the post has at least two engagement signals (e.g., question + strong opinion, '
                'or prediction + concrete example).'
            )
        return prompt

    def schedule_post_performance_checks(self, uri: str) -> None:
        for delay in (3600, 21600, 86400):
            self.bot._spawn_background(self.bot.delayed_performance_check(uri, delay))

