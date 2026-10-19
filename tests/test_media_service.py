#!/usr/bin/env python3
"""Hermetic tests for MediaService (health/media/auth thin-shell extract)."""

from __future__ import annotations

import ast
import asyncio
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from media_service import MediaPorts, MediaService  # noqa: E402
from url_safety import UnsafeURLError  # noqa: E402


@dataclass
class _BlobResp:
    blob: Dict[str, Any] = field(default_factory=lambda: {"ref": "blob-1"})


@dataclass
class _Post:
    text: str
    content_type: str = "news"
    embed: Any = None
    url: Any = None
    image_url: Any = None


class FakeMedia:
    def __init__(
        self,
        *,
        unsafe_url: bool = False,
        upload_ok: bool = True,
        empty_data_path: bool = False,
    ) -> None:
        self.unsafe_url = unsafe_url
        self.upload_ok = upload_ok
        self.empty_data_path = empty_data_path
        self.calls: List[str] = []
        self.errors = 0
        self._session = MagicMock()

    def as_ports(self) -> MediaPorts:
        fake = self

        async def ensure_http():
            fake.calls.append("ensure_http")

        def validate(url: str) -> str:
            fake.calls.append(f"validate:{url}")
            if fake.unsafe_url:
                raise UnsafeURLError("blocked")
            return url

        async def upload_blob(data: bytes):
            fake.calls.append(f"upload_blob:{len(data)}")
            if not fake.upload_ok:
                raise RuntimeError("upload failed")
            return _BlobResp()

        async def media_upload_execute(fn, *args, **kwargs):
            fake.calls.append("media_upload_execute")
            if asyncio.iscoroutinefunction(fn):
                return await fn(*args, **kwargs)
            result = fn(*args, **kwargs)
            if asyncio.iscoroutine(result):
                return await result
            return result

        # Minimal aiohttp-like response for URL download path
        resp = AsyncMock()
        resp.status = 200
        resp.headers = {
            "content-type": "image/png",
            "content-length": "12",
        }
        resp.read = AsyncMock(return_value=b"PNGFAKEBYTES")
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        fake._session.get = MagicMock(return_value=resp)

        return MediaPorts(
            ensure_http=ensure_http,
            get_http_session=lambda: fake._session,
            media_upload_execute=media_upload_execute,
            upload_blob=upload_blob,
            validate_outbound_url=validate,
            create_post=lambda text, content_type="news": _Post(
                text=text, content_type=content_type
            ),
            bump_errors=lambda: setattr(fake, "errors", fake.errors + 1)
            or fake.calls.append("bump_errors"),
        )


class TestMediaServiceNoBotImport(unittest.TestCase):
    def test_module_has_no_bluesky_bot_v2_import(self) -> None:
        path = APP_DIR / "media_service.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn("bluesky_bot_v2", alias.name)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn("bluesky_bot_v2", node.module or "")


class TestMediaServiceGates(unittest.TestCase):
    def test_unsafe_url_returns_none(self) -> None:
        fake = FakeMedia(unsafe_url=True)
        svc = MediaService(fake.as_ports())
        blob = asyncio.run(svc.upload_image_to_bluesky("http://evil.local/x.png"))
        self.assertIsNone(blob)
        self.assertNotIn("media_upload_execute", fake.calls)

    def test_empty_image_data_returns_none(self) -> None:
        fake = FakeMedia()
        svc = MediaService(fake.as_ports())
        blob = asyncio.run(svc.upload_image_data_to_bluesky(b""))
        self.assertIsNone(blob)
        self.assertNotIn("media_upload_execute", fake.calls)


class TestMediaServiceHappyPath(unittest.TestCase):
    def test_upload_image_data_happy(self) -> None:
        fake = FakeMedia()
        svc = MediaService(fake.as_ports())
        blob = asyncio.run(svc.upload_image_data_to_bluesky(b"raw-bytes"))
        self.assertEqual(blob, {"ref": "blob-1"})
        self.assertIn("media_upload_execute", fake.calls)
        self.assertIn("upload_blob:9", fake.calls)

    def test_create_post_with_image_happy(self) -> None:
        fake = FakeMedia()
        svc = MediaService(fake.as_ports())
        post = asyncio.run(
            svc.create_post_with_image("hello", "https://cdn.example/a.png")
        )
        self.assertIsNotNone(post)
        self.assertEqual(post.embed["$type"], "app.bsky.embed.images")
        self.assertEqual(post.embed["images"][0]["image"], {"ref": "blob-1"})


if __name__ == "__main__":
    unittest.main()
