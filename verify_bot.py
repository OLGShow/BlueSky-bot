#!/usr/bin/env python3
"""Root shim: delegate to app/verify_bot.py (SoT)."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
TARGET = REPO_ROOT / "app" / "verify_bot.py"
sys.argv[0] = str(TARGET)
runpy.run_path(str(TARGET), run_name="__main__")
