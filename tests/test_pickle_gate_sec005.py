#!/usr/bin/env python3
"""
SEC-005: Gate unsafe pickle.load — refuse unless ALLOW_PICKLE_MIGRATION=1,
with path safety checks when allowed.

Hermetic: uses tempfile; no network.

Run:
  python tests/test_pickle_gate_sec005.py
  python -m unittest tests.test_pickle_gate_sec005
"""

from __future__ import annotations

import os
import pickle
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from state_service import StateService, _PICKLE_MAX_BYTES  # noqa: E402


@dataclass
class FakeMemory:
    successful_posts: List = field(default_factory=list)
    failed_posts: List = field(default_factory=list)
    interaction_patterns: Dict = field(default_factory=dict)
    trending_topics: Dict = field(default_factory=dict)
    user_relationships: Dict = field(default_factory=dict)
    content_performance: Dict = field(default_factory=dict)
    last_update: datetime = field(default_factory=datetime.now)
    published_content_hashes: Set = field(default_factory=set)
    published_urls: Set = field(default_factory=set)
    repost_performance: List = field(default_factory=list)
    viral_posts: List = field(default_factory=list)
    engagement_metrics: Dict = field(default_factory=dict)
    ab_results: Dict = field(default_factory=dict)
    topic_outcomes: Dict = field(default_factory=dict)
    source_outcomes: Dict = field(default_factory=dict)
    pattern_blacklist: List = field(default_factory=list)


def _write_pickle(path: str, marker: str = "sec005-marker") -> None:
    mem = FakeMemory(successful_posts=[{"text": marker}])
    with open(path, "wb") as f:
        pickle.dump(mem, f)


class TestPickleGateSec005(unittest.TestCase):
    def test_refuses_without_flag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pkl = os.path.join(tmpdir, "bot_memory.pkl")
            json_path = os.path.join(tmpdir, "bot_memory.json")
            _write_pickle(pkl)
            env = {k: v for k, v in os.environ.items() if k != "ALLOW_PICKLE_MIGRATION"}
            with mock.patch.dict(os.environ, env, clear=True):
                with mock.patch("state_service.pickle.load") as load_mock:
                    svc = StateService(path=json_path, legacy_pickle=pkl)
                    mem = svc.load(FakeMemory)
                    load_mock.assert_not_called()
            self.assertEqual(mem.successful_posts, [])
            self.assertTrue(os.path.isfile(pkl))
            self.assertFalse(os.path.exists(json_path))

    def test_flag_zero_refuses(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pkl = os.path.join(tmpdir, "bot_memory.pkl")
            json_path = os.path.join(tmpdir, "bot_memory.json")
            _write_pickle(pkl)
            with mock.patch.dict(os.environ, {"ALLOW_PICKLE_MIGRATION": "0"}):
                with mock.patch("state_service.pickle.load") as load_mock:
                    svc = StateService(path=json_path, legacy_pickle=pkl)
                    mem = svc.load(FakeMemory)
                    load_mock.assert_not_called()
            self.assertEqual(mem.successful_posts, [])

    def test_allowed_migrates_and_archives(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pkl = os.path.join(tmpdir, "bot_memory.pkl")
            json_path = os.path.join(tmpdir, "bot_memory.json")
            _write_pickle(pkl, marker="migrated-ok")
            with mock.patch.dict(os.environ, {"ALLOW_PICKLE_MIGRATION": "1"}):
                svc = StateService(path=json_path, legacy_pickle=pkl)
                mem = svc.load(FakeMemory)
            self.assertEqual(mem.successful_posts[0]["text"], "migrated-ok")
            self.assertTrue(os.path.isfile(json_path))
            self.assertFalse(os.path.exists(pkl))
            self.assertTrue(os.path.isfile(pkl + ".migrated"))

    def test_rejects_symlink_when_allowed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            real = os.path.join(tmpdir, "real.pkl")
            link = os.path.join(tmpdir, "link.pkl")
            json_path = os.path.join(tmpdir, "bot_memory.json")
            _write_pickle(real)
            try:
                os.symlink(real, link)
            except OSError:
                self.skipTest("symlink creation not available on this host")
            self.assertTrue(os.path.islink(link))
            with mock.patch.dict(os.environ, {"ALLOW_PICKLE_MIGRATION": "1"}):
                with mock.patch("state_service.pickle.load") as load_mock:
                    svc = StateService(path=json_path, legacy_pickle=link)
                    mem = svc.load(FakeMemory)
                    load_mock.assert_not_called()
            self.assertEqual(mem.successful_posts, [])
            self.assertFalse(os.path.exists(json_path))

    def test_validate_rejects_oversized(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pkl = os.path.join(tmpdir, "bot_memory.pkl")
            _write_pickle(pkl)
            big = mock.Mock(
                st_uid=os.getuid() if hasattr(os, "getuid") else 0,
                st_size=_PICKLE_MAX_BYTES + 1,
            )
            with mock.patch("state_service.os.path.islink", return_value=False):
                with mock.patch("state_service.os.path.isfile", return_value=True):
                    with mock.patch("state_service.os.stat", return_value=big):
                        with self.assertRaises(ValueError) as ctx:
                            StateService._validate_pickle_path(pkl)
            self.assertIn("too large", str(ctx.exception))


def run_sec005_assertions() -> None:
    """Callable from verify_bot.py — raises AssertionError on failure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pkl = os.path.join(tmpdir, "bot_memory.pkl")
        json_path = os.path.join(tmpdir, "bot_memory.json")
        _write_pickle(pkl, marker="verify-gate")

        env = {k: v for k, v in os.environ.items() if k != "ALLOW_PICKLE_MIGRATION"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("state_service.pickle.load") as load_mock:
                svc = StateService(path=json_path, legacy_pickle=pkl)
                mem = svc.load(FakeMemory)
                assert not load_mock.called, "pickle.load must not run without flag"
        assert mem.successful_posts == [], "expected fresh memory when gated"

        with mock.patch.dict(os.environ, {"ALLOW_PICKLE_MIGRATION": "1"}):
            svc = StateService(path=json_path, legacy_pickle=pkl)
            mem = svc.load(FakeMemory)
        assert mem.successful_posts[0]["text"] == "verify-gate"
        assert os.path.isfile(json_path)
        assert not os.path.exists(pkl)
        assert os.path.isfile(pkl + ".migrated")


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    unittest.main(verbosity=2)
