#!/usr/bin/env python3
"""
OpenRouter adapter for BlueSky bot (OpenAI-compatible chat completions).
Drop-in replacement for PollinationsAI text generation.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import random
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)


class OpenRouterAI:
    """Text + image generation via OpenRouter; drop-in for PollinationsAI."""

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
    IMAGE_URL = "https://openrouter.ai/api/v1/images"
    DEFAULT_MODEL = "openai/gpt-4o-mini"
    # ~$0.008–0.015/img — fits ~$2–5/mo at a few posts/day
    DEFAULT_IMAGE_MODEL = "openai/gpt-image-1-mini"

    # Role keys used by the bot → OpenRouter model ids
    MODELS = {
        "creative": "openai/gpt-4o-mini",
        "powerful": "openai/gpt-4o-mini",
        "smart": "openai/gpt-4o-mini",
        "coder": "openai/gpt-4o-mini",
        "reasoning": "openai/gpt-4o-mini",
        "fast": "openai/gpt-4o-mini",
        "search": "openai/gpt-4o-mini",
        "multilingual": "openai/gpt-4o-mini",
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "creative",
        language: str = "en",
        model_id: Optional[str] = None,
    ):
        self.api_key = (api_key or os.getenv("OPENROUTER_API_KEY") or "").strip()
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is required for OpenRouterAI")

        self.default_model_key = default_model
        self.language = language
        self.model_id = (model_id or os.getenv("OPENROUTER_MODEL") or self.DEFAULT_MODEL).strip()
        self.image_model_id = (
            os.getenv("OPENROUTER_IMAGE_MODEL") or self.DEFAULT_IMAGE_MODEL
        ).strip()
        self.image_quality = (os.getenv("OPENROUTER_IMAGE_QUALITY") or "low").strip().lower()
        # All bot roles use the configured OpenRouter model (default: gpt-4o-mini)
        self.MODELS = {k: self.model_id for k in type(self).MODELS}

        self._session: Optional[aiohttp.ClientSession] = None
        self.stats = {
            "requests_made": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "models_used": {},
            "images_generated": 0,
            "image_cost_usd": 0.0,
        }

        logger.info(
            "OpenRouter adapter initialized (%s), text=%s, image=%s, quality=%s",
            language.upper(),
            self.model_id,
            self.image_model_id,
            self.image_quality,
        )

    def _get_model_name(self, model_key: str) -> str:
        return self.MODELS.get(model_key, self.model_id)

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            # Image models can take 30–90s
            timeout = aiohttp.ClientTimeout(total=120, connect=30)
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "https://github.com/bluesky-bot"),
                    "X-Title": os.getenv("OPENROUTER_APP_TITLE", "BlueSky-Bot"),
                    "User-Agent": "BlueSky-Bot/2.1 (OpenRouter)",
                },
            )
        return self._session

    @staticmethod
    def _aspect_ratio(width: int, height: int) -> str:
        if not width or not height:
            return "1:1"
        ratio = width / height
        if 0.9 <= ratio <= 1.1:
            return "1:1"
        if ratio >= 1.6:
            return "16:9"
        if ratio <= 0.65:
            return "9:16"
        if ratio >= 1.2:
            return "4:3"
        return "3:4"

    @staticmethod
    def _decode_image_b64(b64_value: str) -> Optional[bytes]:
        if not b64_value:
            return None
        raw = b64_value.strip()
        if raw.startswith("data:") and "," in raw:
            raw = raw.split(",", 1)[1]
        try:
            return base64.b64decode(raw)
        except Exception:
            return None

    async def close_session(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_system_prompt(self, content_type: str = "general") -> str:
        if self.language == "ru":
            prompts = {
                "general": (
                    "Ты креативный помощник для социальных сетей. Пиши увлекательный, "
                    "продуманный контент на русском языке. Фокусируйся на технологиях, "
                    "инновациях и значимых дискуссиях для сообщества BlueSky."
                ),
                "comment": (
                    "Ты дружелюбный пользователь социальных сетей. Пиши короткие, "
                    "позитивные комментарии на русском языке с эмодзи. Будь искренним."
                ),
                "post": (
                    "Ты создатель контента для социальных сетей. Пиши на русском языке, "
                    "используй эмодзи, делай контент интересным для технической аудитории."
                ),
            }
        else:
            prompts = {
                "general": (
                    "You are a creative social media assistant. Write engaging, thoughtful "
                    "content in English for the BlueSky community (tech, innovation, discussion)."
                ),
                "comment": (
                    "You are a friendly social media user. Write short, positive comments "
                    "in English with emojis. Be authentic and engaging."
                ),
                "post": (
                    "You are a social media content creator. Write in English, use emojis, "
                    "make content engaging for a tech-savvy audience."
                ),
            }
        return prompts.get(content_type, prompts["general"])

    def _generate_fallback_content(self, prompt: str) -> str:
        prompt_lower = prompt.lower()
        if self.language == "ru":
            if "коммент" in prompt_lower or "ответ" in prompt_lower:
                options = ["Интересная мысль! 🤔", "Спасибо за пост! ✨", "Отличная точка зрения! 👍"]
            else:
                options = [
                    "🤖 Исследуем идеи в технологиях и инновациях! Что вас сегодня вдохновляет?",
                    "🚀 Каждый день — шанс узнать что-то новое. О чём думаете?",
                ]
        else:
            if "comment" in prompt_lower or "reply" in prompt_lower:
                options = ["Interesting point! 🤔", "Thanks for sharing! ✨", "Great insight! 👍"]
            else:
                options = [
                    "🤖 Exploring ideas in tech and innovation! What's exciting you today?",
                    "🚀 Every day is a chance to learn something new. What's on your mind?",
                ]
        return random.choice(options)

    async def generate_content(
        self,
        prompt: str,
        model_key: str = None,
        system_role: str = None,
        json_output: bool = False,
        seed: Optional[int] = None,
    ) -> str:
        self.stats["requests_made"] += 1
        model_key = model_key or self.default_model_key
        model_name = self._get_model_name(model_key)

        if not system_role:
            system_role = self._get_system_prompt("general")
        if json_output:
            system_role = (
                f"{system_role}\n\nReply with valid JSON only. "
                "No markdown fences, no commentary outside JSON."
            )

        messages = [
            {"role": "system", "content": system_role},
            {"role": "user", "content": prompt},
        ]
        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.7 if not json_output else 0.4,
            "max_tokens": 900 if json_output else 600,
        }
        if json_output:
            payload["response_format"] = {"type": "json_object"}
        if seed is not None:
            payload["seed"] = seed

        try:
            logger.debug("OpenRouter request: model=%s json=%s", model_name, json_output)
            text = await self._chat_completion(payload)
            if not text:
                raise RuntimeError("Empty response from OpenRouter")

            self.stats["successful_requests"] += 1
            self.stats["models_used"][model_name] = self.stats["models_used"].get(model_name, 0) + 1
            logger.info("OpenRouter OK (%s chars, model=%s)", len(text), model_name)
            return text.strip()
        except Exception as e:
            self.stats["failed_requests"] += 1
            logger.warning("OpenRouter error: %s", e)
            return self._generate_fallback_content(prompt)

    async def _chat_completion(self, payload: Dict[str, Any]) -> Optional[str]:
        max_retries = 3
        base_delay = 2
        session = await self.get_session()

        for attempt in range(max_retries):
            try:
                async with session.post(self.BASE_URL, json=payload) as response:
                    body = await response.text()
                    if response.status == 429:
                        delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                        logger.warning(
                            "OpenRouter 429, retry %s/%s in %.1fs",
                            attempt + 1,
                            max_retries,
                            delay,
                        )
                        if attempt < max_retries - 1:
                            await asyncio.sleep(delay)
                            continue
                        return None

                    if response.status >= 400:
                        logger.warning("OpenRouter HTTP %s: %s", response.status, body[:300])
                        if attempt < max_retries - 1 and response.status >= 500:
                            await asyncio.sleep(base_delay * (attempt + 1))
                            continue
                        return None

                    data = await response.json(content_type=None)
                    choices = data.get("choices") or []
                    if not choices:
                        logger.warning("OpenRouter empty choices: %s", body[:300])
                        return None
                    message = choices[0].get("message") or {}
                    content = message.get("content")
                    if isinstance(content, list):
                        # Some providers return content parts
                        parts = []
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                parts.append(part.get("text") or "")
                            elif isinstance(part, str):
                                parts.append(part)
                        content = "".join(parts)
                    return (content or "").strip() or None
            except asyncio.TimeoutError:
                logger.warning("OpenRouter timeout (%s/%s)", attempt + 1, max_retries)
                if attempt < max_retries - 1:
                    await asyncio.sleep(base_delay * (attempt + 1))
            except Exception as e:
                logger.warning("OpenRouter request failed (%s/%s): %s", attempt + 1, max_retries, e)
                if attempt < max_retries - 1:
                    await asyncio.sleep(base_delay * (attempt + 1))
        return None

    async def generate_comment(self, post_text: str, comment_style: str = "supportive") -> str:
        if self.language == "ru":
            style_prompts = {
                "supportive": f"Напиши короткий поддерживающий комментарий к посту (макс. 80 символов): {post_text[:200]}",
                "question": f"Задай умный уточняющий вопрос к посту (макс. 80 символов): {post_text[:200]}",
                "addition": f"Дополни мысль из поста полезной информацией (макс. 80 символов): {post_text[:200]}",
            }
        else:
            style_prompts = {
                "supportive": f"Write a short supportive comment for this post (max 80 characters): {post_text[:200]}",
                "question": f"Ask a smart follow-up question about this post (max 80 characters): {post_text[:200]}",
                "addition": f"Add useful information to complement this post (max 80 characters): {post_text[:200]}",
            }
        prompt = style_prompts.get(comment_style, style_prompts["supportive"])
        return await self.generate_content(
            prompt=prompt,
            model_key="fast",
            system_role=self._get_system_prompt("comment"),
        )

    async def generate_post_content(self, topic: str, post_type: str = "general") -> str:
        if self.language == "ru":
            type_prompts = {
                "motivational": f"Создай мотивационный пост на тему '{topic}' (до 280 символов) с эмодзи",
                "news": f"Напиши информационный пост-новость о '{topic}' (до 280 символов)",
                "tip": f"Поделись полезным советом по теме '{topic}' (до 280 символов)",
                "question": f"Создай вопрос для обсуждения на тему '{topic}' (до 280 символов)",
                "general": f"Создай интересный пост на тему '{topic}' (до 280 символов) с эмодзи",
            }
        else:
            type_prompts = {
                "motivational": f"Create a motivational post about '{topic}' (up to 280 characters) with emojis",
                "news": f"Write an informative news post about '{topic}' (up to 280 characters)",
                "tip": f"Share a useful tip about '{topic}' (up to 280 characters)",
                "question": f"Create a discussion question about '{topic}' (up to 280 characters)",
                "general": f"Create an interesting post about '{topic}' (up to 280 characters) with emojis",
            }
        model_map = {
            "motivational": "creative",
            "news": "smart",
            "tip": "powerful",
            "question": "creative",
            "general": "creative",
        }
        return await self.generate_content(
            prompt=type_prompts.get(post_type, type_prompts["general"]),
            model_key=model_map.get(post_type, "creative"),
            system_role=self._get_system_prompt("post"),
        )

    async def generate_image_data(
        self,
        prompt: str,
        model: str = "dall-e-3",
        width: int = 1024,
        height: int = 1024,
        seed: Optional[int] = None,
    ) -> Optional[bytes]:
        """Generate image bytes via OpenRouter Image API (POST /api/v1/images)."""
        self.stats["requests_made"] += 1
        # Ignore legacy Pollinations model names like "dall-e-3"
        image_model = self.image_model_id
        if model and "/" in model and not model.startswith("dall"):
            image_model = model

        payload: Dict[str, Any] = {
            "model": image_model,
            "prompt": prompt,
            "aspect_ratio": self._aspect_ratio(width, height),
        }
        # gpt-image-* supports quality; keeps cost ~$0.002–0.009/image
        if self.image_quality and "gpt-image" in image_model:
            payload["quality"] = self.image_quality
        if seed is not None:
            payload["seed"] = seed
        # Prefer jpeg when model allows (smaller uploads to BlueSky)
        if "flux" in image_model or "riverflow" in image_model:
            payload["output_format"] = "jpeg"

        try:
            logger.debug("OpenRouter image: model=%s prompt=%s...", image_model, prompt[:60])
            image_bytes, cost = await self._generate_image(payload)
            if not image_bytes:
                raise RuntimeError("Empty image payload from OpenRouter")

            self.stats["successful_requests"] += 1
            self.stats["images_generated"] += 1
            if cost is not None:
                self.stats["image_cost_usd"] += float(cost)
            key = f"image_{image_model}"
            self.stats["models_used"][key] = self.stats["models_used"].get(key, 0) + 1
            logger.info(
                "OpenRouter image OK (%s bytes, model=%s, cost=$%s)",
                len(image_bytes),
                image_model,
                f"{cost:.4f}" if cost is not None else "?",
            )
            return image_bytes
        except Exception as e:
            self.stats["failed_requests"] += 1
            logger.warning("OpenRouter image error: %s", e)
            return None

    async def _generate_image(
        self, payload: Dict[str, Any]
    ) -> tuple[Optional[bytes], Optional[float]]:
        max_retries = 2
        base_delay = 3
        session = await self.get_session()

        for attempt in range(max_retries):
            try:
                async with session.post(self.IMAGE_URL, json=payload) as response:
                    body = await response.text()
                    if response.status == 429:
                        delay = base_delay * (2 ** attempt) + random.uniform(0.5, 1.5)
                        logger.warning(
                            "OpenRouter image 429, retry %s/%s in %.1fs",
                            attempt + 1,
                            max_retries,
                            delay,
                        )
                        if attempt < max_retries - 1:
                            await asyncio.sleep(delay)
                            continue
                        return None, None

                    if response.status >= 400:
                        logger.warning(
                            "OpenRouter image HTTP %s: %s", response.status, body[:300]
                        )
                        if attempt < max_retries - 1 and response.status >= 500:
                            await asyncio.sleep(base_delay * (attempt + 1))
                            continue
                        return None, None

                    data = await response.json(content_type=None)
                    items = data.get("data") or []
                    if not items:
                        logger.warning("OpenRouter image empty data: %s", body[:300])
                        return None, None

                    item = items[0] or {}
                    b64 = item.get("b64_json") or item.get("b64") or ""
                    # Some providers return a URL instead of base64
                    if not b64 and item.get("url"):
                        async with session.get(item["url"]) as img_resp:
                            if img_resp.status == 200:
                                content = await img_resp.read()
                                usage = data.get("usage") or {}
                                return content, usage.get("cost")
                            return None, None

                    decoded = self._decode_image_b64(b64)
                    usage = data.get("usage") or {}
                    return decoded, usage.get("cost")
            except asyncio.TimeoutError:
                logger.warning(
                    "OpenRouter image timeout (%s/%s)", attempt + 1, max_retries
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(base_delay * (attempt + 1))
            except Exception as e:
                logger.warning(
                    "OpenRouter image request failed (%s/%s): %s",
                    attempt + 1,
                    max_retries,
                    e,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(base_delay * (attempt + 1))
        return None, None

    def get_statistics(self) -> Dict[str, Any]:
        success_rate = 0.0
        if self.stats["requests_made"] > 0:
            success_rate = (self.stats["successful_requests"] / self.stats["requests_made"]) * 100
        return {
            "requests_made": self.stats["requests_made"],
            "total_requests": self.stats["requests_made"],
            "successful_requests": self.stats["successful_requests"],
            "failed_requests": self.stats["failed_requests"],
            "success_rate": f"{success_rate:.1f}%",
            "images_generated": self.stats["images_generated"],
            "image_cost_usd": round(self.stats.get("image_cost_usd", 0.0), 6),
            "models_used": self.stats["models_used"],
            "available_models": list(self.MODELS.keys()),
            "provider": "openrouter",
            "model": self.model_id,
            "image_model": self.image_model_id,
        }

    async def test_connection(self) -> bool:
        try:
            before_fail = self.stats["failed_requests"]
            text = await self.generate_content(
                prompt="Reply with exactly: pong",
                model_key="fast",
                system_role="Reply with one short token only.",
            )
            ok = bool(text) and self.stats["failed_requests"] == before_fail
            if ok:
                logger.info("OpenRouter connection OK (%r)", text[:40])
            else:
                logger.error("OpenRouter connection failed (empty or fallback)")
            return ok
        except Exception as e:
            logger.error("OpenRouter connection failed: %s", e)
            return False
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_session()
