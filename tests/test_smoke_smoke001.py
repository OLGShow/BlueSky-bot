#!/usr/bin/env python3
"""
SMOKE-001: Post-deploy hermetic smoke / dry-run checks.

Default path is network-free (no live Bluesky/OpenRouter). Covers:
  - key module import health
  - bot_config.json presence + required keys
  - DRY_RUN path sanity (env parse + DryRunAction)
  - Bluesky creds fail-fast exit semantics (delegates to VER-001)

Optional live gate (off by default):
  SMOKE_LIVE=1  — requires real-looking creds; performs DNS resolve only
                  (still no API login). Use for post-deploy host wiring.

Run:
  python verify_bot.py --smoke
  python scripts/smoke_check.py
  python -m unittest tests.test_smoke_smoke001
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List, Optional, Sequence
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

BOT_MODULE_PATH = APP_DIR / "bluesky_bot_v2.py"
CONFIG_CANDIDATES = (
    REPO_ROOT / "bot_config.json",
    Path("/etc/bluesky-bot/bot_config.json"),
)

# Modules that must import without network / without Bluesky creds.
KEY_MODULES: Sequence[str] = (
    "state_service",
    "resilience_service",
    "log_sanitizer",
    "engagement_service",
    "content_service",
    "growth_engine",
    "http_session",
    "bot_learning_module",
    "rss_source_manager",
)

REQUIRED_CONFIG_KEYS: Sequence[str] = (
    "post_strategies",
    "bluesky_limits",
    "engagement_settings",
)

_TRUTHY_DRY_RUN = ("true", "1", "yes", "TRUE", "Yes")
_FALSY_DRY_RUN = ("false", "0", "no", "", "FALSE")


def _resolve_config_path() -> Path:
    for path in CONFIG_CANDIDATES:
        if path.is_file():
            return path
    raise AssertionError(
        "bot_config.json not found; checked: "
        + ", ".join(str(p) for p in CONFIG_CANDIDATES)
    )


def _parse_dry_run(value: Optional[str]) -> bool:
    """Mirror bluesky_bot_v2 dry_run env semantics (hermetic, no bot ctor)."""
    return (value or "false").lower() in ("true", "1", "yes")


def check_key_module_imports() -> None:
    failed: List[str] = []
    for name in KEY_MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 — collect all import failures
            failed.append(f"{name}: {exc}")
    assert not failed, "key module import failures:\n  - " + "\n  - ".join(failed)


def check_config_presence() -> None:
    path = _resolve_config_path()
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert isinstance(data, dict), f"{path} must be a JSON object"
    missing = [k for k in REQUIRED_CONFIG_KEYS if k not in data]
    assert not missing, f"{path} missing required keys: {missing}"


def check_dry_run_path_sanity() -> None:
    assert BOT_MODULE_PATH.is_file(), f"missing {BOT_MODULE_PATH}"
    src = BOT_MODULE_PATH.read_text(encoding="utf-8", errors="replace")
    assert "DRY_RUN" in src, "bot must read DRY_RUN env"
    assert "DryRunAction" in src, "bot must wire DryRunAction for dry-run mode"

    tree = ast.parse(src, filename=str(BOT_MODULE_PATH))
    dry_run_assign_found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Attribute) and t.attr == "dry_run":
                    dry_run_assign_found = True
    assert dry_run_assign_found, "self.dry_run assignment must exist in bluesky_bot_v2.py"

    for raw in _TRUTHY_DRY_RUN:
        assert _parse_dry_run(raw) is True, f"DRY_RUN={raw!r} should be truthy"
    for raw in _FALSY_DRY_RUN:
        assert _parse_dry_run(raw) is False, f"DRY_RUN={raw!r} should be falsy"

    from growth_engine import DryRunAction

    with tempfile.TemporaryDirectory() as tmp:
        action = DryRunAction()
        action.log("post", text="smoke")
        assert len(action.actions) == 1
        report = Path(tmp) / "dry_run_report.json"
        action.save(str(report))
        assert report.is_file(), "DryRunAction.save must write report"
        payload = json.loads(report.read_text(encoding="utf-8"))
        assert payload[0]["action"] == "post"


def check_failfast_creds_exit() -> None:
    from tests.test_bluesky_creds_failfast_ver001 import run_creds_failfast_ver001_assertions

    run_creds_failfast_ver001_assertions()


def check_optional_live_gate() -> None:
    """Gated by SMOKE_LIVE=1. DNS-only; no Bluesky login / API calls."""
    flag = (os.getenv("SMOKE_LIVE") or "").strip().lower()
    if flag not in ("1", "true", "yes"):
        return

    handle = (os.getenv("BLUESKY_HANDLE") or "").strip()
    password = (os.getenv("BLUESKY_PASSWORD") or "").strip()
    assert handle and password, "SMOKE_LIVE=1 requires BLUESKY_HANDLE and BLUESKY_PASSWORD"
    assert "your-" not in handle and "your-" not in password, (
        "SMOKE_LIVE=1 rejects placeholder Bluesky credentials"
    )

    # Host wiring only — no authenticated API traffic.
    try:
        infos = socket.getaddrinfo("bsky.social", 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise AssertionError(f"SMOKE_LIVE DNS resolve failed for bsky.social: {exc}") from exc
    assert infos, "SMOKE_LIVE: getaddrinfo returned empty for bsky.social"


def run_smoke001_assertions(*, include_live: Optional[bool] = None) -> None:
    """
    Callable from verify_bot / scripts/smoke_check — raises AssertionError on failure.

    include_live:
      None  → honour SMOKE_LIVE env (default off)
      True  → force live gate
      False → skip live gate even if SMOKE_LIVE set
    """
    check_key_module_imports()
    check_config_presence()
    check_dry_run_path_sanity()
    check_failfast_creds_exit()

    if include_live is True:
        with mock.patch.dict(os.environ, {"SMOKE_LIVE": "1"}, clear=False):
            check_optional_live_gate()
    elif include_live is False:
        with mock.patch.dict(os.environ, {"SMOKE_LIVE": "0"}, clear=False):
            check_optional_live_gate()
    else:
        check_optional_live_gate()


class TestSmokeSmoke001(unittest.TestCase):
    def test_key_module_imports(self):
        check_key_module_imports()

    def test_config_presence(self):
        check_config_presence()

    def test_dry_run_path_sanity(self):
        check_dry_run_path_sanity()

    def test_failfast_creds_exit(self):
        check_failfast_creds_exit()

    def test_live_gate_skipped_by_default(self):
        with mock.patch.dict(os.environ, {"SMOKE_LIVE": ""}, clear=False):
            check_optional_live_gate()  # no-op / must not raise

    def test_run_smoke001_assertions_hermetic(self):
        run_smoke001_assertions(include_live=False)


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    unittest.main(verbosity=2)
