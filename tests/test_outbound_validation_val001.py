#!/usr/bin/env python3
"""
VAL-001 / TEST-001: outbound text validation at publish boundary.

Hermetic: content_service helpers only — no network / atproto.

Covers:
  - empty / None / whitespace-only reject
  - control-char strip (keep \\n / \\t)
  - truncate to 300 graphemes
  - valid short text unchanged

Run:
  python tests/test_outbound_validation_val001.py
  python -m unittest tests.test_outbound_validation_val001
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from content_service import (  # noqa: E402
    BLUESKY_MAX_GRAPHEMES,
    OutboundContentError,
    sanitize_outbound_text,
    split_graphemes,
    truncate_to_graphemes,
    validate_outbound_text,
)


class TestOutboundValidationVal001(unittest.TestCase):
    def test_rejects_none(self):
        with self.assertRaises(OutboundContentError) as ctx:
            validate_outbound_text(None)
        self.assertIn("empty", str(ctx.exception).lower())

    def test_rejects_empty_string(self):
        with self.assertRaises(OutboundContentError):
            validate_outbound_text("")

    def test_rejects_whitespace_only(self):
        with self.assertRaises(OutboundContentError):
            validate_outbound_text("   \t  \n  ")

    def test_rejects_controls_only_after_sanitize(self):
        # NUL + other C0 controls → empty after sanitize+strip
        with self.assertRaises(OutboundContentError):
            validate_outbound_text("\x00\x01\x02\x1f\x7f")

    def test_strips_control_chars_keeps_newline_tab(self):
        raw = "hello\x00world\nline2\tand\x1fmore"
        cleaned = sanitize_outbound_text(raw)
        self.assertEqual(cleaned, "helloworld\nline2\tandmore")
        self.assertNotIn("\x00", cleaned)
        self.assertNotIn("\x1f", cleaned)
        self.assertIn("\n", cleaned)
        self.assertIn("\t", cleaned)
        self.assertEqual(
            validate_outbound_text(raw),
            "helloworld\nline2\tandmore",
        )

    def test_valid_short_text_unchanged(self):
        text = "Normal Bluesky post with a question?"
        self.assertEqual(validate_outbound_text(text), text)

    def test_strips_outer_whitespace(self):
        self.assertEqual(
            validate_outbound_text("  padded post  "),
            "padded post",
        )

    def test_truncate_to_max_graphemes_default(self):
        # ASCII 1 grapheme per char — over 300 must truncate with ellipsis
        long_text = "a" * 400
        result = validate_outbound_text(long_text)
        clusters = split_graphemes(result)
        self.assertLessEqual(len(clusters), BLUESKY_MAX_GRAPHEMES)
        self.assertTrue(result.endswith("…"))
        self.assertLess(len(clusters), 400)

    def test_truncate_helper_respects_budget(self):
        text = "word " * 100  # well over 300
        truncated = truncate_to_graphemes(text, max_graphemes=300)
        self.assertLessEqual(len(split_graphemes(truncated)), 300)
        self.assertTrue(truncated.endswith("…"))

    def test_truncate_false_rejects_overlong(self):
        long_text = "x" * 350
        with self.assertRaises(OutboundContentError) as ctx:
            validate_outbound_text(long_text, truncate=False)
        self.assertIn("grapheme", str(ctx.exception).lower())

    def test_combining_mark_counts_as_one_cluster_approx(self):
        # e + combining acute → one cluster in our approx splitter
        text = "e\u0301"  # é as base+mark
        clusters = split_graphemes(text)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(validate_outbound_text(text), text)

    def test_exactly_max_graphemes_unchanged(self):
        text = "z" * BLUESKY_MAX_GRAPHEMES
        self.assertEqual(validate_outbound_text(text), text)
        self.assertEqual(len(split_graphemes(text)), BLUESKY_MAX_GRAPHEMES)

    def test_prepare_via_content_service_delegate(self):
        from content_service import ContentService

        svc = ContentService(bot=object())
        self.assertEqual(svc.prepare_outbound_text("ok post"), "ok post")
        with self.assertRaises(OutboundContentError):
            svc.prepare_outbound_text("   ")


def run_val001_assertions() -> None:
    """Callable from verify/acceptance — raises AssertionError on failure."""
    try:
        validate_outbound_text("")
        raise AssertionError("empty must raise")
    except OutboundContentError:
        pass

    cleaned = validate_outbound_text("hi\x00there")
    assert cleaned == "hithere", cleaned

    long_text = "a" * 400
    out = validate_outbound_text(long_text)
    assert len(split_graphemes(out)) <= BLUESKY_MAX_GRAPHEMES
    assert out.endswith("…")


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    unittest.main(verbosity=2)
