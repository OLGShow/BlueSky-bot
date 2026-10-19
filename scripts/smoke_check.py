#!/usr/bin/env python3
"""
SMOKE-001 operator entrypoint — thin wrapper around ``verify_bot.py --smoke``.

Hermetic by default (no live network). Non-zero exit on any failed check.

Usage:
  python scripts/smoke_check.py
  python scripts/smoke_check.py --help

Equivalent:
  python verify_bot.py --smoke

Optional live DNS gate (still no API login):
  SMOKE_LIVE=1 python scripts/smoke_check.py

Exit codes:
  0 — all smoke checks passed
  1 — one or more checks failed
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.chdir(REPO_ROOT)


def main(argv: Optional[List[str]] = None) -> None:
    # Preserve caller argv after the script name; force --smoke.
    rest = list(sys.argv[1:] if argv is None else argv)
    if "--smoke" not in rest:
        rest.insert(0, "--smoke")

    import verify_bot

    verify_bot.main(rest)


if __name__ == "__main__":
    main()
