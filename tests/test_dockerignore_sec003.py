#!/usr/bin/env python3
"""
SEC-003: hermetic checks that .dockerignore excludes nested secrets and that
Dockerfile does not bake credentials via ARG/ENV.

No docker daemon required — parse ignore file + small path matcher + Dockerfile scan.

Run:
  python tests/test_dockerignore_sec003.py
  python -m unittest tests.test_dockerignore_sec003
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
DOCKERFILE = REPO_ROOT / "Dockerfile"

# Patterns that MUST appear (as literal lines after strip) in .dockerignore.
REQUIRED_PATTERNS = (
    "**/.env",
    "**/.env.*",
    "**/session.json",
    "**/bot_memory.json",
    "**/bot_memory.pkl",
    "**/bot_memory*",
    "**/action_ledger.jsonl",
    "**/credentials.json",
    "**/*.pem",
    "**/*.key",
    "**/*secret*",
    "secrets/",
    "packaging/_stage/",
    "etc/",
    "opt/**/.env",
    "opt/**/.env.*",
    "opt/**/session.json",
    "opt/**/bot_memory*",
    "opt/**/action_ledger.jsonl",
    "opt/**/venv/",
)

# Paths that must be excluded from the Docker build context (files need not exist).
MUST_EXCLUDE = (
    "etc/bluesky-bot/.env",
    "opt/bluesky-bot/session.json",
    "opt/bluesky-bot/.env",
    "opt/bluesky-bot/bot_memory.json",
    "foo/bar/.env",
    "nested/session.json",
    "nested/credentials.json",
    "certs/tls.pem",
    "keys/id_rsa.key",
    "config/my_secret.json",
    "secrets/api_token.txt",
    "packaging/_stage/bluesky_bot_v2.py",
)

# Paths that should remain eligible for COPY (not matched by secret/state rules).
# Note: broad patterns like etc/ exclude everything under etc/; SoT lives under app/.
MUST_NOT_EXCLUDE = (
    "app/bluesky_bot_v2.py",
    "requirements.txt",
    "env.example",
    "Dockerfile",
)

# ARG/ENV lines whose variable names look like secrets.
_RE_ARG_ENV_LINE = re.compile(r"(?im)^\s*(ARG|ENV)\s+(.+?)(?:\s*#.*)?$")
_RE_SECRET_TOKEN = re.compile(r"(?:PASSWORD|API_KEY|SECRET)", re.IGNORECASE)
# Split ENV key=value [key2=value2] / ARG NAME[=default]
_RE_ENV_ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=")
_RE_ARG_NAME = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)")


def load_dockerignore_lines() -> list[str]:
    if not DOCKERIGNORE.is_file():
        raise FileNotFoundError(f"SEC-003 .dockerignore missing: {DOCKERIGNORE}")
    text = DOCKERIGNORE.read_text(encoding="utf-8", errors="replace")
    lines: list[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        lines.append(s)
    return lines


def _glob_segment_to_re(segment: str) -> str:
    """Convert one path segment glob (* and ?) to a regex (no **/)."""
    out: list[str] = []
    for ch in segment:
        if ch == "*":
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(ch))
    return "".join(out)


def dockerignore_pattern_to_regex(pattern: str) -> re.Pattern[str]:
    """
    Approximate Docker .dockerignore matching for hermetic tests.

    Supports:
      - ** spanning zero or more directories
      - * / ? within a segment
      - trailing / as directory prefix (etc/ → etc and etc/...)
      - patterns without / matching basename anywhere (Docker/gitignore-like)
    """
    p = pattern.replace("\\", "/").strip()
    dir_only = p.endswith("/")
    if dir_only:
        p = p.rstrip("/")

    # Basename-only patterns (no slash): match at any depth.
    if "/" not in p and "**" not in p:
        body = _glob_segment_to_re(p)
        rx = rf"(?:^|.*/){body}"
        if dir_only:
            rx = rf"(?:{rx})(?:/.*)?"
        return re.compile(rf"^{rx}$")

    parts: list[str] = []
    i = 0
    while i < len(p):
        if p.startswith("**/", i):
            parts.append("(?:.*/)?")
            i += 3
            continue
        if p[i : i + 2] == "**" and (i + 2 == len(p) or p[i + 2] == "/"):
            # trailing ** or **/ already handled; lone ** at end
            parts.append(".*")
            i += 2
            if i < len(p) and p[i] == "/":
                i += 1
            continue
        # consume until next /
        j = p.find("/", i)
        if j < 0:
            seg = p[i:]
            i = len(p)
        else:
            seg = p[i:j]
            i = j + 1
        if seg == "**":
            parts.append("(?:.*/)?")
            continue
        parts.append(_glob_segment_to_re(seg))
        if j >= 0:
            parts.append("/")

    body = "".join(parts)
    # Collapse accidental double slashes from **/ handling
    body = re.sub(r"/+", "/", body)
    if dir_only:
        rx = rf"^{body}(?:/.*)?$"
    else:
        rx = rf"^{body}$"
    return re.compile(rx)


def path_excluded_by_dockerignore(patterns: list[str], rel_path: str) -> bool:
    """Return True if any non-negated pattern would exclude rel_path."""
    path = rel_path.replace("\\", "/").lstrip("./")
    for pattern in patterns:
        if pattern.startswith("!"):
            continue
        if dockerignore_pattern_to_regex(pattern).match(path):
            return True
    return False


def dockerfile_secret_arg_env_hits(text: str) -> list[str]:
    """Return ARG/ENV variable names that contain PASSWORD|API_KEY|SECRET."""
    hits: list[str] = []
    for m in _RE_ARG_ENV_LINE.finditer(text):
        kind = m.group(1).upper()
        rest = m.group(2).strip()
        # Skip Dockerfile ENV key without '=' when it's a continuation form is rare;
        # handle KEY=val and KEY val (ARG default).
        names: list[str] = []
        if "=" in rest:
            # Possibly multiple KEY=value pairs on one ENV line
            for token in rest.split():
                am = _RE_ENV_ASSIGN.match(token)
                if am:
                    names.append(am.group(1))
                else:
                    # ENV NAME value  (space-separated form): first token is name
                    nm = _RE_ARG_NAME.match(token)
                    if nm and not names:
                        names.append(nm.group(1))
                        break
        else:
            nm = _RE_ARG_NAME.match(rest)
            if nm:
                names.append(nm.group(1))
        for name in names:
            if _RE_SECRET_TOKEN.search(name):
                hits.append(f"{kind} {name}")
    return hits


class TestDockerignoreSec003(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patterns = load_dockerignore_lines()
        cls.pattern_set = set(cls.patterns)
        if not DOCKERFILE.is_file():
            raise unittest.SkipTest("Dockerfile missing")
        cls.dockerfile = DOCKERFILE.read_text(encoding="utf-8", errors="replace")

    def test_required_patterns_present(self):
        for pattern in REQUIRED_PATTERNS:
            with self.subTest(pattern=pattern):
                self.assertIn(
                    pattern,
                    self.pattern_set,
                    f"{pattern!r} missing from .dockerignore",
                )

    def test_nested_secrets_excluded_by_matcher(self):
        for path in MUST_EXCLUDE:
            with self.subTest(path=path):
                self.assertTrue(
                    path_excluded_by_dockerignore(self.patterns, path),
                    f"{path} should be excluded by .dockerignore patterns",
                )

    def test_app_sources_not_excluded(self):
        for path in MUST_NOT_EXCLUDE:
            with self.subTest(path=path):
                self.assertFalse(
                    path_excluded_by_dockerignore(self.patterns, path),
                    f"{path} should NOT be excluded by .dockerignore",
                )

    def test_etc_env_and_opt_session_specifically(self):
        """Acceptance paths from SEC-003 plan."""
        self.assertTrue(
            path_excluded_by_dockerignore(
                self.patterns, "etc/bluesky-bot/.env"
            ),
            "etc/bluesky-bot/.env must be dockerignored",
        )
        self.assertTrue(
            path_excluded_by_dockerignore(
                self.patterns, "opt/bluesky-bot/session.json"
            ),
            "opt/bluesky-bot/session.json must be dockerignored",
        )

    def test_dockerfile_no_secret_arg_env(self):
        hits = dockerfile_secret_arg_env_hits(self.dockerfile)
        self.assertEqual(
            hits,
            [],
            f"Dockerfile must not declare secret ARG/ENV: {hits}",
        )


def run_sec003_assertions() -> None:
    """Callable from verify_bot.py — raises AssertionError / FileNotFoundError on failure."""
    patterns = load_dockerignore_lines()
    pattern_set = set(patterns)

    for pattern in REQUIRED_PATTERNS:
        assert pattern in pattern_set, f"{pattern!r} missing from .dockerignore"

    for path in (
        "etc/bluesky-bot/.env",
        "opt/bluesky-bot/session.json",
    ):
        assert path_excluded_by_dockerignore(patterns, path), (
            f"{path} should be excluded by .dockerignore"
        )

    if not DOCKERFILE.is_file():
        raise FileNotFoundError(f"SEC-003 Dockerfile missing: {DOCKERFILE}")
    hits = dockerfile_secret_arg_env_hits(
        DOCKERFILE.read_text(encoding="utf-8", errors="replace")
    )
    assert not hits, f"Dockerfile has secret ARG/ENV: {hits}"


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    unittest.main(verbosity=2)
