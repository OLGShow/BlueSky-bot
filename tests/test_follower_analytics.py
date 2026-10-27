#!/usr/bin/env python3
"""W1-005: follower_analytics hermetic tests (cohort math + state I/O)."""

from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
MODULE_PATH = APP_DIR / "follower_analytics.py"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


class TestFollowerAnalyticsNoBotImport(unittest.TestCase):
    def test_module_has_no_bluesky_bot_v2_import(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(MODULE_PATH))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "bluesky_bot_v2")
                    self.assertFalse(alias.name.startswith("bluesky_bot_v2."))
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                self.assertNotEqual(mod, "bluesky_bot_v2")
                self.assertFalse(mod.startswith("bluesky_bot_v2."))


class TestDiffCohorts(unittest.TestCase):
    def test_new_returned_churned(self) -> None:
        from follower_analytics import diff_cohorts

        prev = {"a", "b", "c"}
        curr = {"b", "c", "d", "e"}
        ever_seen = {"a", "b", "c", "e"}  # e left earlier, returns now

        result = diff_cohorts(prev, curr, ever_seen=ever_seen)

        self.assertEqual(result["churned"], {"a"})
        self.assertEqual(result["new"], {"d"})
        self.assertEqual(result["returned"], {"e"})

    def test_without_ever_seen_all_additions_are_new(self) -> None:
        from follower_analytics import diff_cohorts

        result = diff_cohorts({"a"}, {"a", "b", "c"}, ever_seen=None)
        self.assertEqual(result["new"], {"b", "c"})
        self.assertEqual(result["returned"], set())
        self.assertEqual(result["churned"], set())

    def test_empty_sets(self) -> None:
        from follower_analytics import diff_cohorts

        result = diff_cohorts(set(), set())
        self.assertEqual(result["new"], set())
        self.assertEqual(result["returned"], set())
        self.assertEqual(result["churned"], set())

    def test_full_churn(self) -> None:
        from follower_analytics import diff_cohorts

        result = diff_cohorts({"x", "y"}, set(), ever_seen={"x", "y"})
        self.assertEqual(result["churned"], {"x", "y"})
        self.assertEqual(result["new"], set())
        self.assertEqual(result["returned"], set())


class TestApplySnapshotBaselineAndChurnReturn(unittest.TestCase):
    def test_first_snapshot_is_baseline(self) -> None:
        from follower_analytics import apply_snapshot, empty_state

        state, report = apply_snapshot(
            empty_state(),
            ["did:plc:alice", "did:plc:bob"],
            ts="2026-10-27T10:00:00+00:00",
        )

        self.assertTrue(report["baseline"])
        self.assertEqual(report["new"], 0)
        self.assertEqual(report["returned"], 0)
        self.assertEqual(report["churned"], 0)
        self.assertEqual(report["curr_size"], 2)
        self.assertEqual(report["prev_size"], 0)
        self.assertEqual(report["net"], 2)
        self.assertEqual(sorted(state["prev"]), ["did:plc:alice", "did:plc:bob"])
        self.assertEqual(sorted(state["ever_seen"]), ["did:plc:alice", "did:plc:bob"])
        self.assertEqual(state["churned_history"], [])
        self.assertEqual(state["updated_at"], "2026-10-27T10:00:00+00:00")
        self.assertEqual(len(state["history"]), 1)
        self.assertTrue(state["history"][0]["baseline"])

    def test_second_snapshot_detects_churn_and_return(self) -> None:
        from follower_analytics import apply_snapshot, empty_state

        # Baseline: alice, bob, carol
        state, _ = apply_snapshot(
            empty_state(),
            ["did:plc:alice", "did:plc:bob", "did:plc:carol"],
            ts="2026-10-27T10:00:00+00:00",
        )
        # Intermediate: carol churns (alice, bob remain)
        state, mid = apply_snapshot(
            state,
            ["did:plc:alice", "did:plc:bob"],
            ts="2026-10-27T11:00:00+00:00",
        )
        self.assertFalse(mid["baseline"])
        self.assertEqual(mid["churned"], 1)
        self.assertEqual(mid["new"], 0)
        self.assertEqual(mid["returned"], 0)
        self.assertIn("did:plc:carol", state["churned_history"])

        # Third: dave is new, carol returns, bob churns
        state, report = apply_snapshot(
            state,
            ["did:plc:alice", "did:plc:carol", "did:plc:dave"],
            ts="2026-10-27T12:00:00+00:00",
        )

        self.assertFalse(report["baseline"])
        self.assertEqual(report["new"], 1)
        self.assertEqual(report["returned"], 1)
        self.assertEqual(report["churned"], 1)
        self.assertEqual(report["curr_size"], 3)
        self.assertEqual(report["prev_size"], 2)
        self.assertEqual(report["net"], 1)
        self.assertEqual(report["new_sample"], ["did:plc:dave"])
        self.assertEqual(report["returned_sample"], ["did:plc:carol"])
        self.assertEqual(report["churned_sample"], ["did:plc:bob"])
        self.assertNotIn("did:plc:carol", state["churned_history"])
        self.assertIn("did:plc:bob", state["churned_history"])
        self.assertEqual(
            sorted(state["prev"]),
            ["did:plc:alice", "did:plc:carol", "did:plc:dave"],
        )


class TestHashBucketMode(unittest.TestCase):
    def test_normalize_and_hash_did(self) -> None:
        from follower_analytics import (
            MODE_HASH_BUCKET,
            hash_did,
            normalize_id,
            to_id_set,
        )

        did = "did:plc:alice"
        expected = hash_did(did)
        self.assertEqual(len(expected), 16)
        self.assertEqual(normalize_id(did, MODE_HASH_BUCKET), expected)
        self.assertEqual(to_id_set([did, did, ""], MODE_HASH_BUCKET), {expected})

    def test_apply_snapshot_stores_hashes_not_raw_dids(self) -> None:
        from follower_analytics import (
            MODE_HASH_BUCKET,
            apply_snapshot,
            empty_state,
            hash_did,
        )

        state0 = empty_state(MODE_HASH_BUCKET)
        dids1 = ["did:plc:alice", "did:plc:bob"]
        state, baseline = apply_snapshot(
            state0, dids1, ts="2026-10-27T10:00:00+00:00"
        )
        self.assertTrue(baseline["baseline"])
        self.assertEqual(state["mode"], MODE_HASH_BUCKET)
        hashed = sorted(hash_did(d) for d in dids1)
        self.assertEqual(state["prev"], hashed)
        for raw in dids1:
            self.assertNotIn(raw, state["prev"])
            self.assertNotIn(raw, state["ever_seen"])

        # Churn bob, add carol
        state, report = apply_snapshot(
            state,
            ["did:plc:alice", "did:plc:carol"],
            ts="2026-10-27T11:00:00+00:00",
        )
        self.assertEqual(report["churned"], 1)
        self.assertEqual(report["new"], 1)
        self.assertEqual(report["returned"], 0)
        self.assertEqual(report["churned_sample"], [hash_did("did:plc:bob")])
        self.assertEqual(report["new_sample"], [hash_did("did:plc:carol")])


class TestStateIOTempfile(unittest.TestCase):
    def test_save_load_roundtrip(self) -> None:
        from follower_analytics import (
            apply_snapshot,
            empty_state,
            load_state,
            save_state,
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "learning_followers_cohort.json"
            state, _ = apply_snapshot(
                empty_state(),
                ["did:plc:a", "did:plc:b"],
                ts="2026-10-27T10:00:00+00:00",
            )
            save_state(path, state)
            self.assertTrue(path.is_file())

            loaded = load_state(path)
            self.assertEqual(loaded["mode"], "full")
            self.assertEqual(sorted(loaded["prev"]), ["did:plc:a", "did:plc:b"])
            self.assertEqual(loaded["updated_at"], "2026-10-27T10:00:00+00:00")
            self.assertEqual(len(loaded["history"]), 1)

    def test_load_missing_returns_empty(self) -> None:
        from follower_analytics import load_state

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            loaded = load_state(path)
            self.assertEqual(loaded["prev"], [])
            self.assertEqual(loaded["ever_seen"], [])
            self.assertIsNone(loaded["updated_at"])

    def test_load_corrupt_returns_empty(self) -> None:
        from follower_analytics import load_state

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{not-json", encoding="utf-8")
            loaded = load_state(path)
            self.assertEqual(loaded["prev"], [])

    def test_tracker_persist_roundtrip(self) -> None:
        from follower_analytics import FollowerCohortTracker, load_state

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cohort.json"
            tracker = FollowerCohortTracker(str(path))
            report = tracker.apply(
                ["did:plc:x", "did:plc:y"],
                ts="2026-10-27T09:00:00+00:00",
            )
            self.assertTrue(report["baseline"])
            self.assertTrue(path.is_file())

            disk = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(sorted(disk["prev"]), ["did:plc:x", "did:plc:y"])

            again = FollowerCohortTracker(str(path))
            self.assertEqual(sorted(again.state["prev"]), ["did:plc:x", "did:plc:y"])
            report2 = again.apply(
                ["did:plc:x", "did:plc:z"],
                ts="2026-10-27T10:00:00+00:00",
            )
            self.assertEqual(report2["churned"], 1)
            self.assertEqual(report2["new"], 1)

            reloaded = load_state(path)
            self.assertEqual(sorted(reloaded["prev"]), ["did:plc:x", "did:plc:z"])


if __name__ == "__main__":
    unittest.main()
