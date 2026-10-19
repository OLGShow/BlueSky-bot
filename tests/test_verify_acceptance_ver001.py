#!/usr/bin/env python3
"""
VER-001: Consolidated acceptance net for ignore hygiene + session perms + pickle gate.

SSOT: delegates to run_sec001 / run_sec003 / run_sec004 / run_sec005.
Audit IDs: [S2], [S3], [S4] (plus gitignore SEC-001 for nested ignore coverage).

Run:
  python tests/test_verify_acceptance_ver001.py
  python -m unittest tests.test_verify_acceptance_ver001
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def run_ver001_assertions() -> None:
    """Callable from verify_bot.py — raises AssertionError on failure."""
    from tests.test_gitignore_sec001 import run_sec001_assertions
    from tests.test_dockerignore_sec003 import run_sec003_assertions
    from tests.test_session_store_chmod_sec004 import run_sec004_assertions
    from tests.test_pickle_gate_sec005 import run_sec005_assertions

    run_sec001_assertions()
    run_sec003_assertions()
    run_sec004_assertions()
    run_sec005_assertions()


class TestVerifyAcceptanceVer001(unittest.TestCase):
    def test_consolidated_acceptance(self):
        run_ver001_assertions()


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    unittest.main(verbosity=2)
