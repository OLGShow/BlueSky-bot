#!/usr/bin/env python3
"""W1-002 / W1-004: api_incident_log hermetic tests."""

from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


class TestApiIncidentLogNoBotImport(unittest.TestCase):
    def test_acyclic(self) -> None:
        path = APP_DIR / "api_incident_log.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "bluesky_bot_v2")
                    self.assertFalse(alias.name.startswith("bluesky_bot_v2."))
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                self.assertNotEqual(mod, "bluesky_bot_v2")
                self.assertFalse(mod.startswith("bluesky_bot_v2."))


class TestClassifyError(unittest.TestCase):
    def test_429(self) -> None:
        from api_incident_log import ERROR_CLASS_429, classify_error

        self.assertEqual(classify_error("HTTP 429 Too Many Requests"), ERROR_CLASS_429)
        self.assertEqual(classify_error("rate limit exceeded"), ERROR_CLASS_429)
        self.assertEqual(classify_error(Exception("ratelimit")), ERROR_CLASS_429)

    def test_auth_required(self) -> None:
        from api_incident_log import ERROR_CLASS_AUTH_REQUIRED, classify_error

        self.assertEqual(classify_error("AuthRequired"), ERROR_CLASS_AUTH_REQUIRED)
        self.assertEqual(classify_error("auth_required"), ERROR_CLASS_AUTH_REQUIRED)
        self.assertEqual(classify_error("401 Unauthorized"), ERROR_CLASS_AUTH_REQUIRED)

    def test_account_suspended_takedown(self) -> None:
        from api_incident_log import ERROR_CLASS_ACCOUNT_SUSPENDED, classify_error

        self.assertEqual(
            classify_error("AccountTakedown"), ERROR_CLASS_ACCOUNT_SUSPENDED
        )
        self.assertEqual(
            classify_error("account_takedown notice"), ERROR_CLASS_ACCOUNT_SUSPENDED
        )
        self.assertEqual(
            classify_error("AccountSuspended"), ERROR_CLASS_ACCOUNT_SUSPENDED
        )
        self.assertEqual(
            classify_error("account suspended by moderator"),
            ERROR_CLASS_ACCOUNT_SUSPENDED,
        )

    def test_forbidden(self) -> None:
        from api_incident_log import ERROR_CLASS_FORBIDDEN, classify_error

        self.assertEqual(classify_error("Forbidden"), ERROR_CLASS_FORBIDDEN)
        self.assertEqual(classify_error("HTTP 403"), ERROR_CLASS_FORBIDDEN)

    def test_network(self) -> None:
        from api_incident_log import ERROR_CLASS_NETWORK, classify_error

        self.assertEqual(classify_error("ConnectionError: reset"), ERROR_CLASS_NETWORK)
        self.assertEqual(classify_error("request timed out"), ERROR_CLASS_NETWORK)
        self.assertEqual(classify_error("dns lookup failed"), ERROR_CLASS_NETWORK)

    def test_other(self) -> None:
        from api_incident_log import ERROR_CLASS_OTHER, classify_error

        self.assertEqual(classify_error("unexpected server bug"), ERROR_CLASS_OTHER)
        self.assertEqual(classify_error(None), ERROR_CLASS_OTHER)
        self.assertEqual(classify_error(""), ERROR_CLASS_OTHER)
        self.assertEqual(classify_error("   "), ERROR_CLASS_OTHER)


class TestBuildAndRecordIncident(unittest.TestCase):
    def test_build_incident_event_fields(self) -> None:
        from api_incident_log import ERROR_CLASS_429, build_incident_event

        event = build_incident_event(
            "engage",
            "like",
            status=429,
            message="rate limit",
            did="did:plc:abc",
            uri="at://did:plc:abc/app.bsky.feed.post/xyz",
            extra={"count": 1},
            ts="2026-10-27T00:00:00+00:00",
        )
        self.assertEqual(event["stage"], "engage")
        self.assertEqual(event["op"], "like")
        self.assertEqual(event["status"], 429)
        self.assertEqual(event["error_class"], ERROR_CLASS_429)
        self.assertEqual(event["message"], "rate limit")
        self.assertEqual(event["did"], "did:plc:abc")
        self.assertIn("uri", event)
        self.assertEqual(event["extra"]["count"], 1)
        self.assertEqual(event["ts"], "2026-10-27T00:00:00+00:00")

    def test_build_prefers_exc_class_over_status(self) -> None:
        from api_incident_log import (
            ERROR_CLASS_ACCOUNT_SUSPENDED,
            build_incident_event,
        )

        event = build_incident_event(
            "auth",
            "login",
            status=403,
            exc=Exception("AccountTakedown"),
        )
        self.assertEqual(event["error_class"], ERROR_CLASS_ACCOUNT_SUSPENDED)
        self.assertEqual(event["status"], 403)

    def test_record_incident_writes_jsonl(self) -> None:
        from api_incident_log import ERROR_CLASS_NETWORK, record_incident

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reports" / "api_incidents.jsonl"
            record_incident(
                "publish",
                "create_post",
                exc=ConnectionError("Connection refused"),
                path=str(path),
            )
            self.assertTrue(path.is_file())
            lines = [
                ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()
            ]
            self.assertEqual(len(lines), 1)
            entry = json.loads(lines[0])
            self.assertEqual(entry["stage"], "publish")
            self.assertEqual(entry["op"], "create_post")
            self.assertEqual(entry["error_class"], ERROR_CLASS_NETWORK)
            self.assertIn("Connection refused", entry["message"])
            self.assertIn("ts", entry)

    def test_record_incident_appends_multiple_lines(self) -> None:
        from api_incident_log import record_incident

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "incidents.jsonl"
            record_incident("a", "op1", message="one", path=str(path))
            record_incident("b", "op2", message="two", path=str(path))
            lines = [
                ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()
            ]
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["stage"], "a")
            self.assertEqual(json.loads(lines[1])["stage"], "b")


class TestAppendIncidentSwallowsErrors(unittest.TestCase):
    def test_append_incident_bad_path_does_not_raise(self) -> None:
        from api_incident_log import append_incident

        # On Windows, a path with an invalid device name / NUL-like reserved
        # segment under a non-writable root is unreliable; use a directory path
        # as the "file" so open(..., "a") fails after makedirs.
        with tempfile.TemporaryDirectory() as tmp:
            bad_as_dir = Path(tmp) / "not_a_file"
            bad_as_dir.mkdir()
            # Passing a directory path makes open(..., "a") raise IsADirectoryError
            # (or PermissionError on some platforms). Must not propagate.
            append_incident(str(bad_as_dir), {"stage": "x", "op": "y"})

    def test_append_incident_impossible_path_does_not_raise(self) -> None:
        from api_incident_log import append_incident

        with tempfile.TemporaryDirectory() as tmp:
            # Parent path is a regular file → makedirs / open must fail, not raise out.
            blocker = Path(tmp) / "blocker"
            blocker.write_text("x", encoding="utf-8")
            bad = blocker / "child" / "incidents.jsonl"
            append_incident(str(bad), {"stage": "z", "op": "z"})


class TestSummarizeIncidents(unittest.TestCase):
    """W1-004: summarize_incidents from JSONL fixtures."""

    DAY = "2026-10-27"
    OTHER_DAY = "2026-10-26"

    def _fixture_events(self) -> list[dict]:
        # Known stage × error_class for DAY:
        #   follow×429: 2, like×429: 3, auth×AccountSuspended: 1, publish×network: 1
        # Other day / bad lines must be ignored or counted as skipped.
        return [
            {
                "ts": f"{self.DAY}T01:00:00+00:00",
                "stage": "follow",
                "op": "create",
                "error_class": "429",
            },
            {
                "ts": f"{self.DAY}T02:00:00Z",
                "stage": "follow",
                "op": "create",
                "error_class": "429",
            },
            {
                "ts": f"{self.DAY}T03:00:00+00:00",
                "stage": "like",
                "op": "like",
                "error_class": "429",
            },
            {
                "ts": f"{self.DAY}T04:00:00+00:00",
                "stage": "like",
                "op": "like",
                "error_class": "429",
            },
            {
                "ts": f"{self.DAY}T05:00:00+00:00",
                "stage": "like",
                "op": "like",
                "error_class": "429",
            },
            {
                "ts": f"{self.DAY}T06:00:00+00:00",
                "stage": "auth",
                "op": "login",
                "error_class": "AccountSuspended",
            },
            {
                "ts": f"{self.DAY}T07:00:00+00:00",
                "stage": "publish",
                "op": "create_post",
                "error_class": "network",
            },
            # Different UTC day — excluded from totals
            {
                "ts": f"{self.OTHER_DAY}T12:00:00+00:00",
                "stage": "follow",
                "op": "create",
                "error_class": "429",
            },
        ]

    def test_summarize_stage_error_class_counts(self) -> None:
        from api_incident_log import (
            ERROR_CLASS_429,
            ERROR_CLASS_ACCOUNT_SUSPENDED,
            summarize_incidents,
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "api_incidents.jsonl"
            _write_jsonl(path, self._fixture_events())
            # Corrupt / non-object lines → skipped_lines, not total
            with open(path, "a", encoding="utf-8") as handle:
                handle.write("not-json\n")
                handle.write("42\n")
                handle.write("\n")

            summary = summarize_incidents(str(path), day=self.DAY)

            self.assertEqual(summary["date"], self.DAY)
            self.assertEqual(summary["source"], str(path))
            self.assertEqual(summary["total"], 7)
            self.assertEqual(summary["skipped_lines"], 2)
            self.assertEqual(
                summary["by_stage_error_class"],
                {
                    "auth": {ERROR_CLASS_ACCOUNT_SUSPENDED: 1},
                    "follow": {ERROR_CLASS_429: 2},
                    "like": {ERROR_CLASS_429: 3},
                    "publish": {"network": 1},
                },
            )
            self.assertEqual(summary["by_error_class"][ERROR_CLASS_429], 5)
            self.assertEqual(
                summary["by_error_class"][ERROR_CLASS_ACCOUNT_SUSPENDED], 1
            )
            self.assertEqual(summary["by_stage"]["like"], 3)
            self.assertEqual(summary["by_stage"]["follow"], 2)
            # Top stages sorted by count desc, then stage name
            self.assertEqual(
                summary["top_stages_429"],
                [
                    {"stage": "like", "count": 3},
                    {"stage": "follow", "count": 2},
                ],
            )
            self.assertEqual(
                summary["top_stages_AccountSuspended"],
                [{"stage": "auth", "count": 1}],
            )

    def test_summarize_missing_jsonl_total_zero(self) -> None:
        from api_incident_log import summarize_incidents

        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope" / "missing.jsonl"
            summary = summarize_incidents(str(missing), day=self.DAY)
            self.assertEqual(summary["total"], 0)
            self.assertEqual(summary["skipped_lines"], 0)
            self.assertEqual(summary["by_stage_error_class"], {})
            self.assertEqual(summary["top_stages_429"], [])
            self.assertEqual(summary["top_stages_AccountSuspended"], [])

    def test_summarize_empty_jsonl_total_zero(self) -> None:
        from api_incident_log import summarize_incidents

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.jsonl"
            path.write_text("", encoding="utf-8")
            summary = summarize_incidents(str(path), day=self.DAY)
            self.assertEqual(summary["total"], 0)
            self.assertEqual(summary["by_stage_error_class"], {})
            self.assertEqual(summary["top_stages_429"], [])
            self.assertEqual(summary["top_stages_AccountSuspended"], [])


class TestWriteApiHealthDaily(unittest.TestCase):
    """W1-004: write_api_health_daily artifact shape."""

    DAY = "2026-10-27"

    def test_write_creates_file_with_top_stages(self) -> None:
        from api_incident_log import (
            ERROR_CLASS_429,
            ERROR_CLASS_ACCOUNT_SUSPENDED,
            write_api_health_daily,
        )

        events = [
            {
                "ts": f"{self.DAY}T10:00:00+00:00",
                "stage": "like",
                "op": "like",
                "error_class": ERROR_CLASS_429,
            },
            {
                "ts": f"{self.DAY}T11:00:00+00:00",
                "stage": "like",
                "op": "like",
                "error_class": ERROR_CLASS_429,
            },
            {
                "ts": f"{self.DAY}T12:00:00+00:00",
                "stage": "follow",
                "op": "create",
                "error_class": ERROR_CLASS_429,
            },
            {
                "ts": f"{self.DAY}T13:00:00+00:00",
                "stage": "auth",
                "op": "login",
                "error_class": ERROR_CLASS_ACCOUNT_SUSPENDED,
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jsonl = root / "api_incidents.jsonl"
            out_dir = root / "reports"
            _write_jsonl(jsonl, events)

            out_path = write_api_health_daily(
                str(jsonl), out_dir=out_dir, day=self.DAY
            )

            expected = out_dir / f"api_health_daily_{self.DAY}.json"
            self.assertEqual(out_path, expected)
            self.assertTrue(expected.is_file())

            payload = json.loads(expected.read_text(encoding="utf-8"))
            self.assertEqual(payload["date"], self.DAY)
            self.assertEqual(payload["total"], 4)
            self.assertIn("top_stages_429", payload)
            self.assertIn("top_stages_AccountSuspended", payload)
            self.assertEqual(
                payload["top_stages_429"],
                [
                    {"stage": "like", "count": 2},
                    {"stage": "follow", "count": 1},
                ],
            )
            self.assertEqual(
                payload["top_stages_AccountSuspended"],
                [{"stage": "auth", "count": 1}],
            )
            self.assertEqual(
                payload["by_stage_error_class"]["like"][ERROR_CLASS_429], 2
            )

    def test_write_missing_jsonl_total_zero_no_raise(self) -> None:
        from api_incident_log import write_api_health_daily

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "absent.jsonl"
            out_dir = root / "reports"
            out_path = write_api_health_daily(
                str(missing), out_dir=out_dir, day=self.DAY
            )
            payload = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["total"], 0)
            self.assertEqual(payload["top_stages_429"], [])
            self.assertEqual(payload["top_stages_AccountSuspended"], [])

    def test_write_empty_jsonl_total_zero_no_raise(self) -> None:
        from api_incident_log import write_api_health_daily

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jsonl = root / "empty.jsonl"
            jsonl.write_text("", encoding="utf-8")
            out_dir = root / "reports"
            out_path = write_api_health_daily(
                str(jsonl), out_dir=out_dir, day=self.DAY
            )
            payload = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["total"], 0)
            self.assertEqual(payload["by_stage_error_class"], {})


if __name__ == "__main__":
    unittest.main()
