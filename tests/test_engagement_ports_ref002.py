#!/usr/bin/env python3
"""
REF-001 / REF-002: EngagementService on EngagementPorts — hermetic unit tests.

Fake ports only — no network, atproto, or AutonomousBlueskyBotV2.

Covers:
  - like / repost / follow honor dry_run, ledger, budget, stats, identity
  - EngagementService source has no ``.bot`` attribute use
  - EngagementConfigView.from_mapping, UnlimitedBudget, DryRunGate basics

Run:
  python tests/test_engagement_ports_ref002.py
  python -m unittest tests.test_engagement_ports_ref002
"""

from __future__ import annotations

import ast
import asyncio
import os
import sys
import unittest
from pathlib import Path
from typing import Any, List, Optional, Set

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from engagement_ports import (  # noqa: E402
    DryRunGate,
    EngagementConfigView,
    EngagementIdentityView,
    EngagementPorts,
    UnlimitedBudget,
)
from engagement_service import EngagementService  # noqa: E402

SERVICE_MODULE_PATH = APP_DIR / "engagement_service.py"


# --- Fakes ---


class FakeLedger:
    def __init__(self, present: Optional[Set[str]] = None):
        self._keys: Set[str] = set(present or ())
        self.recorded: List[str] = []

    def contains(self, key: str) -> bool:
        return key in self._keys

    def record(self, key: str) -> None:
        self._keys.add(key)
        self.recorded.append(key)


class FakeBudget:
    def __init__(self, allow: bool = True):
        self.allow = allow
        self.can_spend_calls: List[str] = []
        self.spend_calls: List[str] = []

    def can_spend(self, action: str) -> bool:
        self.can_spend_calls.append(action)
        return self.allow

    def spend(self, action: str) -> None:
        self.spend_calls.append(action)


class FakeDryRunLogger:
    def __init__(self):
        self.entries: List[tuple] = []

    def log(self, action: str, **kwargs: Any) -> None:
        self.entries.append((action, kwargs))


class FakeClient:
    def __init__(self):
        self.likes: List[tuple] = []
        self.reposts: List[tuple] = []
        self.follows: List[str] = []

    async def like(self, uri: str, cid: str) -> Any:
        self.likes.append((uri, cid))
        return None

    async def repost(self, uri: str, cid: str) -> Any:
        self.reposts.append((uri, cid))
        return None

    async def follow(self, did: str) -> Any:
        self.follows.append(did)
        return None


def _make_ports(
    *,
    dry_run: bool = False,
    budget_allow: bool = True,
    ledger_keys: Optional[Set[str]] = None,
    logger: Optional[FakeDryRunLogger] = None,
    mode: str = "open",
    whitelist: Optional[Set[str]] = None,
) -> tuple[EngagementPorts, FakeClient, FakeLedger, FakeBudget, FakeDryRunLogger]:
    client = FakeClient()
    ledger = FakeLedger(ledger_keys)
    budget = FakeBudget(allow=budget_allow)
    dry_logger = logger or FakeDryRunLogger()
    ports = EngagementPorts(
        client=client,
        ledger=ledger,
        budget=budget,
        dry_run=DryRunGate(enabled=dry_run, _logger=dry_logger),
        stats={"likes_given": 0, "reposts_made": 0, "follows_made": 0},
        identity=EngagementIdentityView(
            liked_posts=set(),
            reposted_posts=set(),
            followed_users=set(),
            recent_repost_authors=[],
        ),
        config=EngagementConfigView(
            mode=mode,
            whitelist=frozenset(whitelist or ()),
        ),
    )
    return ports, client, ledger, budget, dry_logger


# --- Port helpers ---


class TestEngagementPortHelpers(unittest.TestCase):
    def test_from_mapping_defaults(self):
        view = EngagementConfigView.from_mapping(None)
        self.assertEqual(view.mode, "open")
        self.assertEqual(view.whitelist, frozenset())

        view_empty = EngagementConfigView.from_mapping({})
        self.assertEqual(view_empty.mode, "open")
        self.assertEqual(view_empty.whitelist, frozenset())

    def test_from_mapping_reads_mode_and_whitelist(self):
        view = EngagementConfigView.from_mapping(
            {
                "engagement_mode": "whitelist_only",
                "engagement_whitelist": ["did:abc", "@handle"],
            }
        )
        self.assertEqual(view.mode, "whitelist_only")
        self.assertEqual(view.whitelist, frozenset({"did:abc", "@handle"}))

    def test_unlimited_budget_always_allows(self):
        budget = UnlimitedBudget()
        self.assertTrue(budget.can_spend("like"))
        self.assertTrue(budget.can_spend("repost"))
        self.assertIsNone(budget.spend("like"))

    def test_dry_run_gate_logs_only_when_enabled_with_logger(self):
        logger = FakeDryRunLogger()
        gate_off = DryRunGate(enabled=False, _logger=logger)
        gate_off.log("like", uri="at://x")
        self.assertEqual(logger.entries, [])

        gate_no_logger = DryRunGate(enabled=True, _logger=None)
        gate_no_logger.log("like", uri="at://x")  # no-op, must not raise

        gate_on = DryRunGate(enabled=True, _logger=logger)
        gate_on.log("like", uri="at://post/1", score=0.9)
        self.assertEqual(len(logger.entries), 1)
        self.assertEqual(logger.entries[0][0], "like")
        self.assertEqual(logger.entries[0][1]["uri"], "at://post/1")


# --- No .bot on EngagementService ---


class TestEngagementServiceNoBotAttr(unittest.TestCase):
    def test_service_source_has_no_bot_attribute(self):
        self.assertTrue(SERVICE_MODULE_PATH.is_file(), f"missing {SERVICE_MODULE_PATH}")
        source = SERVICE_MODULE_PATH.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(SERVICE_MODULE_PATH))

        bot_attrs: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "bot":
                bot_attrs.append(f"line {node.lineno}")
            if isinstance(node, ast.Name) and node.id == "bot":
                # bare name ``bot`` would also indicate coupling
                bot_attrs.append(f"name bot line {node.lineno}")

        self.assertEqual(
            bot_attrs,
            [],
            f"EngagementService must not reference .bot / bot: {bot_attrs}",
        )
        self.assertNotIn("self.bot", source)
        self.assertIn("self._ports", source)

    def test_constructor_takes_ports_not_bot(self):
        ports, *_ = _make_ports()
        svc = EngagementService(ports)
        self.assertFalse(hasattr(svc, "bot"))
        self.assertIs(svc._ports, ports)


# --- like / repost / follow ---


class TestEngagementServiceLike(unittest.TestCase):
    def test_like_live_calls_client_and_updates_ports(self):
        ports, client, ledger, budget, dry_logger = _make_ports(dry_run=False)
        svc = EngagementService(ports)

        ok = asyncio.run(
            svc.like("at://post/1", "cid1", 0.8, author_did="did:author")
        )

        self.assertTrue(ok)
        self.assertEqual(client.likes, [("at://post/1", "cid1")])
        self.assertEqual(dry_logger.entries, [])
        self.assertEqual(ledger.recorded, ["like:at://post/1"])
        self.assertEqual(budget.can_spend_calls, ["like"])
        self.assertEqual(budget.spend_calls, ["like"])
        self.assertEqual(ports.stats["likes_given"], 1)
        self.assertIn("at://post/1", ports.identity.liked_posts)

    def test_like_dry_run_skips_client_logs_and_still_commits(self):
        ports, client, ledger, budget, dry_logger = _make_ports(dry_run=True)
        svc = EngagementService(ports)

        ok = asyncio.run(svc.like("at://post/2", "cid2", 0.5))

        self.assertTrue(ok)
        self.assertEqual(client.likes, [])
        self.assertEqual(len(dry_logger.entries), 1)
        self.assertEqual(dry_logger.entries[0][0], "like")
        self.assertEqual(ledger.recorded, ["like:at://post/2"])
        self.assertEqual(budget.spend_calls, ["like"])
        self.assertEqual(ports.stats["likes_given"], 1)
        self.assertIn("at://post/2", ports.identity.liked_posts)

    def test_like_skipped_when_ledger_contains(self):
        ports, client, ledger, budget, _ = _make_ports(
            ledger_keys={"like:at://post/dup"}
        )
        svc = EngagementService(ports)

        ok = asyncio.run(svc.like("at://post/dup", "cid", 1.0))

        self.assertFalse(ok)
        self.assertEqual(client.likes, [])
        self.assertEqual(ledger.recorded, [])
        self.assertEqual(budget.spend_calls, [])
        self.assertEqual(ports.stats["likes_given"], 0)

    def test_like_skipped_when_already_in_identity(self):
        ports, client, ledger, budget, _ = _make_ports()
        ports.identity.liked_posts.add("at://post/seen")
        svc = EngagementService(ports)

        ok = asyncio.run(svc.like("at://post/seen", "cid", 1.0))

        self.assertFalse(ok)
        self.assertEqual(client.likes, [])
        self.assertEqual(ledger.recorded, [])
        self.assertEqual(budget.spend_calls, [])

    def test_like_skipped_when_budget_exhausted(self):
        ports, client, ledger, budget, _ = _make_ports(budget_allow=False)
        svc = EngagementService(ports)

        ok = asyncio.run(svc.like("at://post/3", "cid3", 0.1))

        self.assertFalse(ok)
        self.assertEqual(client.likes, [])
        self.assertEqual(budget.can_spend_calls, ["like"])
        self.assertEqual(budget.spend_calls, [])
        self.assertEqual(ledger.recorded, [])
        self.assertEqual(ports.stats["likes_given"], 0)


class TestEngagementServiceRepost(unittest.TestCase):
    def test_repost_live_updates_identity_and_authors(self):
        ports, client, ledger, budget, dry_logger = _make_ports(dry_run=False)
        svc = EngagementService(ports)

        ok = asyncio.run(
            svc.repost(
                "at://post/r1",
                "cidr",
                0.7,
                author_did="did:author1",
                author_handle="@a",
            )
        )

        self.assertTrue(ok)
        self.assertEqual(client.reposts, [("at://post/r1", "cidr")])
        self.assertEqual(dry_logger.entries, [])
        self.assertEqual(ledger.recorded, ["repost:at://post/r1"])
        self.assertEqual(budget.spend_calls, ["repost"])
        self.assertEqual(ports.stats["reposts_made"], 1)
        self.assertIn("at://post/r1", ports.identity.reposted_posts)
        self.assertEqual(list(ports.identity.recent_repost_authors), ["did:author1"])

    def test_repost_dry_run_skips_client(self):
        ports, client, ledger, budget, dry_logger = _make_ports(dry_run=True)
        svc = EngagementService(ports)

        ok = asyncio.run(
            svc.repost("at://post/r2", "cidr2", 0.4, author_did="did:a2")
        )

        self.assertTrue(ok)
        self.assertEqual(client.reposts, [])
        self.assertEqual(dry_logger.entries[0][0], "repost")
        self.assertEqual(ledger.recorded, ["repost:at://post/r2"])
        self.assertEqual(budget.spend_calls, ["repost"])
        self.assertEqual(ports.stats["reposts_made"], 1)
        self.assertIn("at://post/r2", ports.identity.reposted_posts)
        self.assertEqual(list(ports.identity.recent_repost_authors), ["did:a2"])

    def test_repost_skipped_when_ledger_or_budget(self):
        ports, client, _, budget, _ = _make_ports(
            ledger_keys={"repost:at://post/x"},
        )
        svc = EngagementService(ports)
        self.assertFalse(
            asyncio.run(svc.repost("at://post/x", "c", 1.0, author_did="did:x"))
        )
        self.assertEqual(client.reposts, [])

        ports2, client2, _, budget2, _ = _make_ports(budget_allow=False)
        svc2 = EngagementService(ports2)
        self.assertFalse(
            asyncio.run(svc2.repost("at://post/y", "c", 1.0, author_did="did:y"))
        )
        self.assertEqual(client2.reposts, [])
        self.assertEqual(budget2.spend_calls, [])


class TestEngagementServiceFollow(unittest.TestCase):
    def test_follow_live_calls_client_and_updates_identity(self):
        ports, client, ledger, budget, dry_logger = _make_ports(dry_run=False)
        svc = EngagementService(ports)

        ok = asyncio.run(
            svc.follow("did:user1", "@user1", source="suggestions")
        )

        self.assertTrue(ok)
        self.assertEqual(client.follows, ["did:user1"])
        self.assertEqual(dry_logger.entries, [])
        self.assertEqual(ledger.recorded, ["follow:did:user1"])
        self.assertEqual(budget.spend_calls, ["follow"])
        self.assertEqual(ports.stats["follows_made"], 1)
        self.assertIn("did:user1", ports.identity.followed_users)

    def test_follow_dry_run_skips_client_and_identity_add(self):
        """follow() only adds to followed_users on the live path (not dry-run)."""
        ports, client, ledger, budget, dry_logger = _make_ports(dry_run=True)
        svc = EngagementService(ports)

        ok = asyncio.run(svc.follow("did:user2", "@user2", source="test"))

        self.assertTrue(ok)
        self.assertEqual(client.follows, [])
        self.assertEqual(dry_logger.entries[0][0], "follow")
        self.assertEqual(dry_logger.entries[0][1].get("did"), "did:user2")
        self.assertEqual(ledger.recorded, ["follow:did:user2"])
        self.assertEqual(budget.spend_calls, ["follow"])
        self.assertEqual(ports.stats["follows_made"], 1)
        self.assertNotIn("did:user2", ports.identity.followed_users)

    def test_follow_skipped_when_already_followed_or_ledger(self):
        ports, client, ledger, budget, _ = _make_ports()
        ports.identity.followed_users.add("did:already")
        svc = EngagementService(ports)

        self.assertFalse(asyncio.run(svc.follow("did:already", "@a")))
        self.assertEqual(client.follows, [])
        self.assertEqual(ledger.recorded, [])
        self.assertEqual(budget.spend_calls, [])

        ports2, client2, _, _, _ = _make_ports(ledger_keys={"follow:did:led"})
        svc2 = EngagementService(ports2)
        self.assertFalse(asyncio.run(svc2.follow("did:led", "@led")))
        self.assertEqual(client2.follows, [])

    def test_follow_skipped_when_budget_exhausted(self):
        ports, client, ledger, budget, _ = _make_ports(budget_allow=False)
        svc = EngagementService(ports)

        ok = asyncio.run(svc.follow("did:nb", "@nb"))

        self.assertFalse(ok)
        self.assertEqual(client.follows, [])
        self.assertEqual(budget.can_spend_calls, ["follow"])
        self.assertEqual(budget.spend_calls, [])
        self.assertEqual(ledger.recorded, [])


class TestEngagementModeGuardViaActions(unittest.TestCase):
    def test_mention_only_blocks_like(self):
        ports, client, ledger, budget, _ = _make_ports(mode="mention_only")
        svc = EngagementService(ports)

        ok = asyncio.run(svc.like("at://p", "c", 1.0, author_did="did:x"))

        self.assertFalse(ok)
        self.assertEqual(client.likes, [])
        self.assertEqual(budget.can_spend_calls, [])
        self.assertEqual(ledger.recorded, [])

    def test_whitelist_only_allows_listed_did(self):
        ports, client, ledger, budget, _ = _make_ports(
            mode="whitelist_only",
            whitelist={"did:ok"},
        )
        svc = EngagementService(ports)

        ok = asyncio.run(
            svc.like("at://p", "c", 1.0, author_did="did:ok")
        )
        self.assertTrue(ok)
        self.assertEqual(client.likes, [("at://p", "c")])

        ports2, client2, _, _, _ = _make_ports(
            mode="whitelist_only",
            whitelist={"did:ok"},
        )
        svc2 = EngagementService(ports2)
        self.assertFalse(
            asyncio.run(svc2.like("at://p2", "c", 1.0, author_did="did:nope"))
        )
        self.assertEqual(client2.likes, [])


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    unittest.main(verbosity=2)
