#!/usr/bin/env python3
"""MediaService — image upload + rich post embeds (thin-shell extract).

Must not import ``bluesky_bot_v2``. The bot remains the composition root and
wires :class:`MediaPorts`.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from url_safety import UnsafeURLError

logger = logging.getLogger(__name__)


@dataclass
class MediaPorts:
    """Dependencies for :class:`MediaService` (pragmatic callables)."""

    ensure_http: Callable[[], Awaitable[Any]]
    get_http_session: Callable[[], Any]
    media_upload_execute: Callable[..., Awaitable[Any]]
    upload_blob: Callable[[bytes], Any]
    validate_outbound_url: Callable[[str], str]
    create_post: Callable[..., Any]
    bump_errors: Callable[[], None]


class MediaService:
    """Download/upload images and build posts with image / link-preview embeds."""

    def __init__(self, ports: MediaPorts) -> None:
        self._ports = ports

    async def upload_image_to_bluesky(self, image_url: str) -> Optional[Dict]:
        """Download image + upload_blob via ``media_upload_execute`` (RETRY-003)."""
        try:
            try:
                image_url = self._ports.validate_outbound_url(image_url)
            except UnsafeURLError as e:
                logger.warning(f"⚠️ Unsafe image URL rejected: {e}")
                return None

            logger.info(f"📸 Загружаю изображение: {image_url}")

            async def _download_and_upload_once():
                await self._ports.ensure_http()
                session = self._ports.get_http_session()
                assert session is not None
                try:
                    async with session.get(image_url, timeout=30) as response:
                        if response.status == 429:
                            raise RuntimeError(
                                f"HTTP 429 rate limit downloading {image_url}"
                            )
                        if response.status >= 500:
                            raise RuntimeError(
                                f"HTTP {response.status} downloading {image_url}"
                            )
                        if response.status != 200:
                            raise RuntimeError(
                                f"HTTP {response.status}: failed to download "
                                f"image {image_url}"
                            )

                        content_length = response.headers.get("content-length")
                        if content_length and int(content_length) > 1000000:
                            raise RuntimeError(
                                f"HTTP 400: image too large ({content_length} bytes)"
                            )

                        image_data = await response.read()
                        content_type = response.headers.get("content-type", "")
                        if not content_type.startswith("image/"):
                            raise RuntimeError(
                                f"HTTP 400: invalid content-type {content_type}"
                            )
                except asyncio.TimeoutError as e:
                    raise TimeoutError(
                        f"Image download timed out for {image_url}"
                    ) from e

                return await self._ports.upload_blob(image_data)

            blob_response = await self._ports.media_upload_execute(
                _download_and_upload_once
            )
            logger.info(f"✅ Изображение загружено: {blob_response.blob}")
            return blob_response.blob

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки изображения: {e}")
            return None

    async def upload_image_data_to_bluesky(
        self, image_data: bytes
    ) -> Optional[Dict]:
        """Upload raw image bytes via ``media_upload_execute`` (RETRY-003)."""
        if not image_data:
            logger.warning("⚠️ Попытка загрузить пустые данные изображения.")
            return None
        try:
            response = await self._ports.media_upload_execute(
                self._ports.upload_blob, image_data
            )
            logger.info("✅ Изображение успешно загружено в BlueSky")
            return response.blob
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки данных изображения в BlueSky: {e}")
            self._ports.bump_errors()
            return None

    async def create_post_with_image(
        self,
        text: str,
        image_url: str,
        alt_text: str = "Изображение к посту",
    ) -> Any:
        """Create a post with an images embed (fallback to text-only)."""
        try:
            blob = await self.upload_image_to_bluesky(image_url)
            if not blob:
                logger.warning("⚠️ Создаю пост без изображения")
                return self._ports.create_post(text, content_type="news")

            post = self._ports.create_post(text, content_type="news")
            post.embed = {
                "$type": "app.bsky.embed.images",
                "images": [{"alt": alt_text, "image": blob}],
            }
            logger.info("✅ Пост с изображением создан")
            return post

        except Exception as e:
            logger.error(f"❌ Ошибка создания поста с изображением: {e}")
            return self._ports.create_post(text, content_type="news")

    async def create_post_with_link_preview(
        self,
        text: str,
        url: str,
        title: str,
        description: str,
        image_url: str = None,
    ) -> Any:
        """Create a post with an external link card (+ optional thumb)."""
        try:
            post = self._ports.create_post(text, content_type="news")
            post.url = url
            post.image_url = image_url

            external_data = {
                "uri": url,
                "title": title[:300],
                "description": description[:1000],
            }

            if image_url:
                blob = await self.upload_image_to_bluesky(image_url)
                if blob:
                    external_data["thumb"] = blob
                    logger.info("✅ Добавлено изображение к карточке ссылки")

            post.embed = {
                "$type": "app.bsky.embed.external",
                "external": external_data,
            }
            return post

        except Exception as e:
            logger.error(f"❌ Ошибка создания поста с карточкой: {e}")
            return self._ports.create_post(text, content_type="news")
