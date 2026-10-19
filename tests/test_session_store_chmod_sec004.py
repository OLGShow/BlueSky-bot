#!/usr/bin/env python3
"""
SEC-004 + SESS-001 / TEST-001: SessionStore chmod 0o600 and best-effort lock.

Hermetic: uses tempfile; no network. On POSIX verifies mode bits; on Windows
asserts save does not raise when chmod is ineffective.

SESS-001: exclusive sidecar lock is non-fatal — save/load/clear still work
when OS locking fails; chmod 0o600 remains intact.

Run:
  python tests/test_session_store_chmod_sec004.py
  python -m unittest tests.test_session_store_chmod_sec004
"""

from __future__ import annotations

import inspect
import json
import logging
import os
import stat
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import state_service  # noqa: E402
from state_service import SessionStore  # noqa: E402

DUMMY_SESSION = "sec004-dummy-session-string"
SESS001_SESSION = "sess001-dummy-session-string"


def session_store_save_source() -> str:
    return inspect.getsource(SessionStore.save)


def _reset_session_lock_warned() -> None:
    state_service._SESSION_LOCK_WARNED = False


class TestSessionStoreChmodSec004(unittest.TestCase):
    def test_save_source_contains_chmod_0o600(self):
        src = session_store_save_source()
        self.assertIn(
            "chmod",
            src,
            "SessionStore.save must call chmod",
        )
        self.assertIn(
            "0o600",
            src,
            "SessionStore.save must use mode 0o600",
        )

    def test_roundtrip_save_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "session.json")
            store = SessionStore(path=path, max_age_hours=24)
            store.save(DUMMY_SESSION)
            loaded = store.load()
            self.assertEqual(loaded, DUMMY_SESSION)

    def test_posix_mode_600_after_save(self):
        if os.name == "nt" or not hasattr(os, "chmod"):
            self.skipTest("POSIX mode bits not enforced on this platform")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "session.json")
            store = SessionStore(path=path, max_age_hours=24)
            store.save(DUMMY_SESSION)
            mode = stat.S_IMODE(os.stat(path).st_mode)
            self.assertEqual(
                mode,
                0o600,
                f"expected 0o600, got {oct(mode)}",
            )

    def test_windows_save_does_not_raise(self):
        """On Windows chmod is often a no-op; save must still succeed."""
        if os.name != "nt":
            self.skipTest("Windows-specific best-effort chmod check")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "session.json")
            store = SessionStore(path=path, max_age_hours=24)
            try:
                store.save(DUMMY_SESSION)
            except Exception as exc:  # noqa: BLE001 — assert no raise
                self.fail(f"SessionStore.save raised on Windows: {exc}")
            self.assertTrue(os.path.isfile(path))
            self.assertEqual(store.load(), DUMMY_SESSION)


class TestSessionStoreLockSess001(unittest.TestCase):
    """SESS-001: best-effort exclusive lock around save/load/clear."""

    def setUp(self):
        _reset_session_lock_warned()

    def tearDown(self):
        _reset_session_lock_warned()

    def test_save_uses_best_effort_lock_helper(self):
        src = session_store_save_source()
        self.assertIn("_best_effort_exclusive_lock", src)
        load_src = inspect.getsource(SessionStore.load)
        clear_src = inspect.getsource(SessionStore.clear)
        self.assertIn("_best_effort_exclusive_lock", load_src)
        self.assertIn("_best_effort_exclusive_lock", clear_src)

    def test_lock_failure_is_non_fatal_save_still_works(self):
        """OS lock raise → warn once, atomic save + load still succeed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "session.json")
            store = SessionStore(path=path, max_age_hours=24)

            if os.name == "nt":
                lock_patch = mock.patch("msvcrt.locking", side_effect=OSError("lock denied"))
            else:
                lock_patch = mock.patch("fcntl.flock", side_effect=OSError("lock denied"))

            with lock_patch:
                with self.assertLogs(state_service.logger, level=logging.WARNING) as cm:
                    store.save(SESS001_SESSION)
                joined = "\n".join(cm.output)
                self.assertIn("file lock unavailable", joined.lower())

            self.assertTrue(os.path.isfile(path))
            self.assertEqual(store.load(), SESS001_SESSION)

    def test_lock_warn_emitted_at_most_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "session.json")
            store = SessionStore(path=path, max_age_hours=24)

            if os.name == "nt":
                lock_patch = mock.patch("msvcrt.locking", side_effect=OSError("busy"))
            else:
                lock_patch = mock.patch("fcntl.flock", side_effect=OSError("busy"))

            with lock_patch:
                with self.assertLogs(state_service.logger, level=logging.WARNING) as cm1:
                    store.save("first")
                with mock.patch.object(state_service.logger, "warning") as warn_mock:
                    store.save("second")
                    # Second failure must not warn again (_SESSION_LOCK_WARNED).
                    for call in warn_mock.call_args_list:
                        msg = str(call)
                        self.assertNotIn("file lock unavailable", msg)

            # First save produced the lock warning.
            self.assertTrue(
                any("file lock unavailable" in line.lower() for line in cm1.output)
            )
            self.assertEqual(store.load(), "second")

    def test_chmod_600_still_ok_after_lock_path(self):
        """Lock wrapper must not drop SEC-004 chmod behavior."""
        if os.name == "nt" or not hasattr(os, "chmod"):
            self.skipTest("POSIX mode bits not enforced on this platform")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "session.json")
            store = SessionStore(path=path, max_age_hours=24)
            store.save(SESS001_SESSION)
            mode = stat.S_IMODE(os.stat(path).st_mode)
            self.assertEqual(mode, 0o600, f"expected 0o600, got {oct(mode)}")

    def test_threaded_concurrent_saves_leave_valid_json(self):
        """Smoke: concurrent saves must not leave corrupt JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "session.json")
            store = SessionStore(path=path, max_age_hours=24)
            errors: list[BaseException] = []

            def worker(n: int) -> None:
                try:
                    for i in range(20):
                        store.save(f"sess-{n}-{i}")
                except BaseException as exc:  # noqa: BLE001
                    errors.append(exc)

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)
                self.assertFalse(t.is_alive(), "thread did not finish")

            self.assertEqual(errors, [], f"worker errors: {errors}")
            self.assertTrue(os.path.isfile(path))
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("session", data)
            self.assertIn("saved_at", data)
            loaded = store.load()
            self.assertIsNotNone(loaded)
            self.assertTrue(str(loaded).startswith("sess-"))

    def test_clear_after_save(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "session.json")
            store = SessionStore(path=path, max_age_hours=24)
            store.save(SESS001_SESSION)
            store.clear()
            self.assertIsNone(store.load())


def run_sec004_assertions() -> None:
    """Callable from verify_bot.py — raises AssertionError on failure."""
    src = session_store_save_source()
    assert "chmod" in src, "SessionStore.save must call chmod"
    assert "0o600" in src, "SessionStore.save must use mode 0o600"
    assert "_best_effort_exclusive_lock" in src, "SESS-001 lock wrapper missing"

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "session.json")
        store = SessionStore(path=path, max_age_hours=24)
        store.save(DUMMY_SESSION)
        loaded = store.load()
        assert loaded == DUMMY_SESSION, f"round-trip failed: {loaded!r}"

        if os.name != "nt" and hasattr(os, "chmod"):
            mode = stat.S_IMODE(os.stat(path).st_mode)
            assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    unittest.main(verbosity=2)
