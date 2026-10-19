#!/usr/bin/env python3
"""
LOG-001 / TEST-001: OpenRouter sk-or-v1- keys masked by SanitizingFilter.

Hermetic: no network. Also re-checks legacy sk- / email / JWT masking.

Run:
  python tests/test_log_sanitizer_log001.py
  python -m unittest tests.test_log_sanitizer_log001
"""

from __future__ import annotations

import logging
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from log_sanitizer import SanitizingFilter  # noqa: E402

# Long enough to match sk-or-v1-[A-Za-z0-9]{20,}
OPENROUTER_KEY = "sk-or-v1-" + ("A" * 32)
OPENAI_STYLE_KEY = "sk-proj-" + ("B" * 24)
JWT_LIKE = "eyJ" + ("C" * 40)


def _record(msg: str, args=None) -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg=msg,
        args=args,
        exc_info=None,
    )


class TestLogSanitizerLog001(unittest.TestCase):
    def setUp(self):
        self.filt = SanitizingFilter()

    def test_openrouter_sk_or_v1_masked_in_msg(self):
        rec = _record(f"auth failed key={OPENROUTER_KEY} retry")
        self.assertTrue(self.filt.filter(rec))
        self.assertNotIn(OPENROUTER_KEY, rec.msg)
        self.assertIn("***", rec.msg)
        self.assertIn("sk-o", rec.msg)  # prefix retained by _mask
        self.assertIn("retry", rec.msg)

    def test_openrouter_key_masked_in_args_tuple(self):
        rec = _record("token=%s", args=(OPENROUTER_KEY,))
        self.assertTrue(self.filt.filter(rec))
        self.assertIsInstance(rec.args, tuple)
        self.assertEqual(len(rec.args), 1)
        self.assertNotEqual(rec.args[0], OPENROUTER_KEY)
        self.assertIn("***", rec.args[0])

    def test_openai_style_sk_still_masked(self):
        rec = _record(f"bearer {OPENAI_STYLE_KEY}")
        self.filt.filter(rec)
        self.assertNotIn(OPENAI_STYLE_KEY, rec.msg)
        self.assertIn("***", rec.msg)

    def test_email_still_masked(self):
        rec = _record("contact user@example.com please")
        self.filt.filter(rec)
        self.assertNotIn("user@example.com", rec.msg)
        self.assertIn("***", rec.msg)

    def test_jwt_like_still_masked(self):
        rec = _record(f"jwt={JWT_LIKE}")
        self.filt.filter(rec)
        self.assertNotIn(JWT_LIKE, rec.msg)
        self.assertIn("***", rec.msg)

    def test_short_sk_or_v1_below_threshold_unchanged(self):
        """Pattern requires 20+ alnum after prefix — stubs below threshold stay."""
        short = "sk-or-v1-short"
        rec = _record(f"probe {short}")
        self.filt.filter(rec)
        self.assertIn(short, rec.msg)

    def test_token_re_source_lists_openrouter_first(self):
        src = (APP_DIR / "log_sanitizer.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("sk-or-v1-", src)
        # OpenRouter alternative must appear before generic sk- so it wins.
        or_idx = src.find("sk-or-v1-")
        sk_idx = src.find("sk-[A-Za-z0-9")
        self.assertGreaterEqual(or_idx, 0)
        self.assertGreaterEqual(sk_idx, 0)
        self.assertLess(or_idx, sk_idx)


def run_log001_assertions() -> None:
    """Callable from verify/acceptance — raises AssertionError on failure."""
    filt = SanitizingFilter()
    rec = _record(f"key={OPENROUTER_KEY}")
    assert filt.filter(rec)
    assert OPENROUTER_KEY not in rec.msg, "OpenRouter key must be masked"
    assert "***" in rec.msg


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    unittest.main(verbosity=2)
