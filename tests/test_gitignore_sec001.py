#!/usr/bin/env python3
"""
SEC-001: hermetic checks that .gitignore covers nested secrets under etc/ and opt/,
without requiring those secret files to exist on disk.

Uses `git check-ignore` (paths may be missing).

Run:
  python tests/test_gitignore_sec001.py
  python -m unittest tests.test_gitignore_sec001
"""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Nested secret/state paths that MUST be ignored (files need not exist).
MUST_IGNORE = (
    "etc/bluesky-bot/.env",
    "opt/bluesky-bot/.env",
    "opt/bluesky-bot/session.json",
    "opt/bluesky-bot/bot_memory.json",
    "opt/bluesky-bot/bot_memory.pkl",
    "etc/bluesky-bot/.env.local",
    "opt/bluesky-bot/action_ledger.jsonl",
)

# Source / template paths that must remain trackable.
MUST_NOT_IGNORE = (
    "opt/bluesky-bot/main.py",
    "env.example",
    "opt/bluesky-bot/env.example",
    "verify_bot.py",
    ".gitignore",
)


def check_ignore(rel_path: str) -> bool:
    """Return True if git would ignore rel_path (exit 0). Files need not exist."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", rel_path],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(
            f"git check-ignore failed for {rel_path!r} "
            f"(exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.returncode == 0


class TestGitignoreSec001(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (REPO_ROOT / ".git").exists() and not (REPO_ROOT / ".gitignore").exists():
            raise unittest.SkipTest("not a git working tree with .gitignore")
        # Prefer real git ignore evaluation; skip only if git is unavailable.
        probe = subprocess.run(
            ["git", "--version"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0:
            raise unittest.SkipTest("git not available")

    def test_nested_secrets_are_ignored(self):
        for path in MUST_IGNORE:
            with self.subTest(path=path):
                self.assertTrue(
                    check_ignore(path),
                    f"{path} should match .gitignore (git check-ignore)",
                )

    def test_source_and_env_example_not_ignored(self):
        for path in MUST_NOT_IGNORE:
            with self.subTest(path=path):
                self.assertFalse(
                    check_ignore(path),
                    f"{path} should NOT be ignored by .gitignore",
                )

    def test_gitignore_declares_nested_env_globs(self):
        """Smoke: key patterns from SEC-001 are present in .gitignore text."""
        text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8", errors="replace")
        for pattern in (
            "**/.env",
            "**/session.json",
            "**/bot_memory.json",
            "etc/bluesky-bot/.env",
            "opt/bluesky-bot/.env",
        ):
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, text, f"{pattern} missing from .gitignore")


def run_sec001_assertions() -> None:
    """Callable from verify_bot.py — raises AssertionError on failure."""
    for path in MUST_IGNORE:
        assert check_ignore(path), f"{path} should be ignored by .gitignore"
    for path in MUST_NOT_IGNORE:
        assert not check_ignore(path), f"{path} should NOT be ignored by .gitignore"


if __name__ == "__main__":
    # Allow `python tests/test_gitignore_sec001.py` from any cwd.
    os.chdir(REPO_ROOT)
    unittest.main(verbosity=2)
