#!/usr/bin/env python3
"""
SEC-002: hermetic content checks for the secret-rotation runbook.

Documentation-only — no network, no credential APIs, no git rewrite.

Run:
  python tests/test_secret_rotation_runbook_sec002.py
  python -m unittest tests.test_secret_rotation_runbook_sec002
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = (
    REPO_ROOT
    / "ai_docs"
    / "develop"
    / "architecture"
    / "2026-09-15-secret-rotation-runbook.md"
)

# OpenAI-style keys: sk- / sk-proj- followed by a long alphanumeric (and _-) run.
# Avoid matching short placeholders like "sk-YOUR_KEY_HERE" by requiring length.
_RE_OPENAI_LOOKALIKE = re.compile(
    r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b",
    re.IGNORECASE,
)

# Bluesky app-password shape: four hyphen-separated 4-char groups (hex-ish / alnum).
# Exclude obvious placeholders (your, xxxx, test, example, etc.).
_RE_BSKY_APP_PW = re.compile(
    r"\b([A-Za-z0-9]{4})-([A-Za-z0-9]{4})-([A-Za-z0-9]{4})-([A-Za-z0-9]{4})\b"
)
_PLACEHOLDER_SEGMENTS = frozenset(
    {
        "xxxx",
        "yyyy",
        "zzzz",
        "aaaa",
        "bbbb",
        "test",
        "demo",
        "fake",
        "null",
        "none",
        "your",
        "pass",
        "word",
        "here",
        "exam",
        "ple1",
        "ple2",
        "key1",
        "key2",
        "abcd",
        "efgh",
        "1234",
        "0000",
        "1111",
    }
)


def load_runbook() -> str:
    if not RUNBOOK.is_file():
        raise FileNotFoundError(f"SEC-002 runbook missing: {RUNBOOK}")
    return RUNBOOK.read_text(encoding="utf-8", errors="replace")


def looks_like_real_secret(text: str) -> list[str]:
    """Return human-readable hits that look like live secrets (not placeholders)."""
    hits: list[str] = []
    for m in _RE_OPENAI_LOOKALIKE.finditer(text):
        token = m.group(0)
        upper = token.upper()
        if any(
            marker in upper
            for marker in (
                "YOUR",
                "EXAMPLE",
                "PLACEHOLDER",
                "REDACTED",
                "CHANGEME",
                "INSERT",
                "REPLACE",
                "XXX",
                "DUMMY",
                "FAKE",
                "SAMPLE",
            )
        ):
            continue
        hits.append(f"openai-lookalike:{token[:12]}…")

    for m in _RE_BSKY_APP_PW.finditer(text):
        segs = [m.group(i).lower() for i in range(1, 5)]
        if any(s in _PLACEHOLDER_SEGMENTS for s in segs):
            continue
        # All-identical segments (aaaa-aaaa-aaaa-aaaa) are documentation fillers.
        if len(set(segs)) == 1:
            continue
        # Require mixed character classes so "your-new-app-password" style
        # hyphenated phrases with non-4-char segments already do not match;
        # for 4-4-4-4, skip if any segment is a common English word stump.
        if all(seg.isalpha() and seg in _PLACEHOLDER_SEGMENTS for seg in segs):
            continue
        hits.append(f"bsky-app-password-lookalike:{m.group(0)}")
    return hits


class TestSecretRotationRunbookSec002(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = load_runbook()
        cls.lower = cls.text.lower()

    def test_runbook_file_exists(self):
        self.assertTrue(RUNBOOK.is_file(), f"expected runbook at {RUNBOOK}")

    def test_mentions_incident_commit_8cfede2(self):
        self.assertIn("8cfede2", self.text)

    def test_mentions_bluesky_password(self):
        self.assertIn("BLUESKY_PASSWORD", self.text)

    def test_mentions_openai_api_key(self):
        self.assertIn("OPENAI_API_KEY", self.text)

    def test_rotation_checklist_concepts(self):
        self.assertRegex(
            self.lower,
            r"rotat(?:e|ion|ing)",
            "runbook should discuss rotate/rotation",
        )
        self.assertIn(
            "checklist",
            self.lower,
            "runbook should include a rotation checklist",
        )

    def test_mentions_filter_repo_or_bfg(self):
        has_filter_repo = "filter-repo" in self.lower or "filter_repo" in self.lower
        has_bfg = re.search(r"\bbfg\b", self.lower) is not None
        self.assertTrue(
            has_filter_repo or has_bfg,
            "runbook should mention git filter-repo and/or BFG",
        )

    def test_force_push_is_manual_not_for_agents(self):
        # Must warn that force-push / history rewrite is operator-only.
        has_force_push = "force-push" in self.lower or "force push" in self.lower
        self.assertTrue(has_force_push, "runbook should mention force-push")

        manual_markers = (
            "manual",
            "human only",
            "operators only",
            "do not automate",
            "not automate",
            "not ask an automated agent",
            "does not authorize agents",
        )
        self.assertTrue(
            any(m in self.lower for m in manual_markers),
            "runbook must state force-push/history rewrite is MANUAL / not for agents",
        )

    def test_no_real_looking_secrets(self):
        hits = looks_like_real_secret(self.text)
        self.assertEqual(
            hits,
            [],
            f"runbook appears to contain secret-like values: {hits}",
        )


def run_sec002_assertions() -> None:
    """Callable from verify_bot.py — raises AssertionError / FileNotFoundError on failure."""
    text = load_runbook()
    lower = text.lower()

    assert "8cfede2" in text, "runbook missing commit id 8cfede2"
    assert "BLUESKY_PASSWORD" in text, "runbook missing BLUESKY_PASSWORD"
    assert "OPENAI_API_KEY" in text, "runbook missing OPENAI_API_KEY"
    assert re.search(r"rotat(?:e|ion|ing)", lower), "runbook missing rotate/rotation"
    assert "checklist" in lower, "runbook missing checklist"
    assert (
        "filter-repo" in lower
        or "filter_repo" in lower
        or re.search(r"\bbfg\b", lower)
    ), "runbook missing filter-repo or BFG"
    assert "force-push" in lower or "force push" in lower, "runbook missing force-push"
    assert any(
        m in lower
        for m in (
            "manual",
            "human only",
            "operators only",
            "do not automate",
            "not automate",
            "not ask an automated agent",
            "does not authorize agents",
        )
    ), "runbook missing MANUAL / not-for-agents warning"
    hits = looks_like_real_secret(text)
    assert not hits, f"runbook contains secret-like values: {hits}"


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    unittest.main(verbosity=2)
