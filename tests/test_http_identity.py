#!/usr/bin/env python3
"""Wave 3.1 / 3.2 stub: http_identity hermetic tests."""

from __future__ import annotations

import ast
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


class TestHttpIdentityAcyclic(unittest.TestCase):
    def test_no_bot_import(self) -> None:
        path = APP_DIR / "http_identity.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "bluesky_bot_v2")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                self.assertNotEqual(mod, "bluesky_bot_v2")
                self.assertFalse(mod.startswith("bluesky_bot_v2."))


class TestGetUserAgent(unittest.TestCase):
    def setUp(self) -> None:
        from http_identity import reset_identity_state

        reset_identity_state()

    def tearDown(self) -> None:
        from http_identity import reset_identity_state

        reset_identity_state()

    def test_defaults_when_empty_config(self) -> None:
        from http_identity import DEFAULT_USER_AGENTS, get_user_agent

        ua = get_user_agent({})
        self.assertIn(ua, DEFAULT_USER_AGENTS)

    def test_empty_user_agents_uses_defaults(self) -> None:
        from http_identity import DEFAULT_USER_AGENTS, get_user_agent

        cfg = {"http_identity": {"rotate": "daily", "user_agents": []}}
        ua = get_user_agent(cfg)
        self.assertIn(ua, DEFAULT_USER_AGENTS)

    def test_custom_pool_and_daily_sticky(self) -> None:
        from http_identity import get_user_agent

        cfg = {
            "http_identity": {
                "rotate": "daily",
                "user_agents": ["UA-A", "UA-B", "UA-C"],
            }
        }
        day1 = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
        day2 = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)

        first = get_user_agent(cfg, now=day1)
        second = get_user_agent(cfg, now=day1)
        self.assertEqual(first, second)
        self.assertIn(first, ("UA-A", "UA-B", "UA-C"))

        next_day = get_user_agent(cfg, now=day2)
        self.assertIn(next_day, ("UA-A", "UA-B", "UA-C"))
        # Same day again still sticky after day change
        self.assertEqual(next_day, get_user_agent(cfg, now=day2))

    def test_process_sticky_forever(self) -> None:
        from http_identity import get_user_agent

        cfg = {
            "http_identity": {
                "rotate": "process",
                "user_agents": ["P1", "P2"],
            }
        }
        with mock.patch("http_identity.random.choice", return_value="P2"):
            first = get_user_agent(cfg)
        second = get_user_agent(
            cfg, now=datetime(2099, 1, 1, tzinfo=timezone.utc)
        )
        self.assertEqual(first, "P2")
        self.assertEqual(second, "P2")

    def test_never_alias_sticky(self) -> None:
        from http_identity import get_user_agent

        cfg = {
            "http_identity": {
                "rotate": "never",
                "user_agents": ["N1"],
            }
        }
        self.assertEqual(get_user_agent(cfg), "N1")
        self.assertEqual(get_user_agent(cfg), "N1")


class TestProxyStub(unittest.TestCase):
    def setUp(self) -> None:
        from http_identity import reset_identity_state

        reset_identity_state()

    def tearDown(self) -> None:
        from http_identity import reset_identity_state

        reset_identity_state()

    def test_disabled_by_default(self) -> None:
        from http_identity import aiohttp_proxy_kwargs, proxy_enabled, resolve_proxy_url

        self.assertFalse(proxy_enabled({}))
        self.assertFalse(proxy_enabled({"proxy": {}}))
        self.assertIsNone(
            resolve_proxy_url(
                {"proxy": {"enabled": False}},
                env={"PROXY_URLS": "http://p1.example:8080"},
            )
        )
        self.assertEqual(aiohttp_proxy_kwargs({"proxy": {"enabled": False}}), {})

    def test_resolve_sticky_when_enabled(self) -> None:
        from http_identity import resolve_proxy_url

        cfg = {"proxy": {"enabled": True, "sticky_hours": 24}}
        env = {"PROXY_URLS": "http://a.example:1, http://b.example:2"}
        now = datetime(2026, 10, 27, 8, 0, tzinfo=timezone.utc)
        first = resolve_proxy_url(cfg, env=env, now=now)
        second = resolve_proxy_url(cfg, env=env, now=now)
        self.assertIn(first, ("http://a.example:1", "http://b.example:2"))
        self.assertEqual(first, second)

    def test_enabled_without_urls_returns_none(self) -> None:
        from http_identity import resolve_proxy_url

        self.assertIsNone(
            resolve_proxy_url(
                {"proxy": {"enabled": True}},
                env={},
            )
        )


class TestAdaptersUseHttpIdentity(unittest.TestCase):
    def test_openrouter_header_calls_get_user_agent(self) -> None:
        from openrouter_adapter import OpenRouterAI

        with mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            adapter = OpenRouterAI(api_key="test-key", bot_config=None)
        with mock.patch(
            "openrouter_adapter.get_user_agent", return_value="UA-TEST"
        ) as mocked:
            headers = adapter._auth_headers()
        mocked.assert_called()
        self.assertEqual(headers["User-Agent"], "UA-TEST")

    def test_pollinations_header_calls_get_user_agent(self) -> None:
        from pollinations_adapter import PollinationsAI

        adapter = PollinationsAI(bot_config={"http_identity": {"user_agents": ["X"]}})
        with mock.patch(
            "pollinations_adapter.get_user_agent", return_value="UA-POL"
        ) as mocked:
            headers = adapter._default_headers()
        mocked.assert_called()
        self.assertEqual(headers["User-Agent"], "UA-POL")

    def test_http_session_passes_ua_header(self) -> None:
        from http_identity import reset_identity_state

        reset_identity_state()
        import http_session as hs

        fake_session = mock.MagicMock()
        with mock.patch.object(hs.aiohttp, "ClientSession", return_value=fake_session) as ctor:
            with mock.patch.object(hs.aiohttp, "TCPConnector"):
                with mock.patch.object(hs.aiohttp, "ClientTimeout"):
                    with mock.patch(
                        "http_session.get_user_agent", return_value="UA-SESSION"
                    ):
                        out = hs.create_http_session({"http_identity": {}})
        self.assertIs(out, fake_session)
        kwargs = ctor.call_args.kwargs
        self.assertEqual(kwargs["headers"]["User-Agent"], "UA-SESSION")


class TestConfigKnobsPresent(unittest.TestCase):
    def test_bot_config_has_http_identity_and_proxy_off(self) -> None:
        import json

        cfg = json.loads((REPO_ROOT / "bot_config.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["http_identity"]["rotate"], "daily")
        self.assertTrue(cfg["http_identity"]["user_agents"])
        self.assertFalse(cfg["proxy"]["enabled"])
        self.assertEqual(cfg["proxy"]["sticky_hours"], 24)
        # Wave constraint: do not flip llm_retro.dry_run
        self.assertTrue(cfg["llm_retro"]["dry_run"])


if __name__ == "__main__":
    unittest.main()
