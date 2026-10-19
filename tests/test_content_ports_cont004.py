#!/usr/bin/env python3
"""
CONT-004: ContentService on ContentPorts — hermetic unit tests.

Fake ports only — no network, atproto, or AutonomousBlueskyBotV2.

Covers:
  - ContentService uses ContentPorts (constructor / ``self._ports``), not bot
  - AST/runtime: no ``self.bot`` / ``.bot`` attribute use
  - ``build_structured_prompt`` respects ``ab_suffix`` and
    ``quality_gate_regen_mode`` via fake PromptContextPort
  - ``schedule_post_performance_checks`` calls spawn with
    ``delayed_performance_check`` delays (3600, 21600, 86400)

Run:
  python tests/test_content_ports_cont004.py
  python -m unittest tests.test_content_ports_cont004
"""

from __future__ import annotations

import ast
import asyncio
import os
import sys
import unittest
from pathlib import Path
from typing import Any, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from content_ports import (  # noqa: E402
    ContentPorts,
    LiveBackgroundScheduler,
    LivePromptContext,
    PromptContextView,
)
from content_service import ContentService, OutboundContentError  # noqa: E402

SERVICE_MODULE_PATH = APP_DIR / "content_service.py"

PERF_CHECK_DELAYS = (3600, 21600, 86400)
STRICT_CONTRACT_MARKER = "STRICT OUTPUT CONTRACT:"
REGEN_MARKER = "The previous attempt was rejected"


# --- Fakes ---


class FakePromptContext:
    """Mutable PromptContextPort stand-in (tracks property reads)."""

    def __init__(
        self,
        *,
        ab_suffix: str = "",
        quality_gate_regen_mode: bool = False,
    ):
        self._ab_suffix = ab_suffix
        self._quality_gate_regen_mode = quality_gate_regen_mode
        self.ab_suffix_reads = 0
        self.regen_reads = 0

    @property
    def ab_suffix(self) -> str:
        self.ab_suffix_reads += 1
        return self._ab_suffix

    @property
    def quality_gate_regen_mode(self) -> bool:
        self.regen_reads += 1
        return self._quality_gate_regen_mode


class FakeScheduler:
    """BackgroundSchedulerPort stand-in — records spawn / delay calls."""

    def __init__(self):
        self.spawn_coros: List[Any] = []
        self.delayed_calls: List[Tuple[str, int]] = []

    def spawn(self, coro: Any) -> None:
        self.spawn_coros.append(coro)
        # Avoid "coroutine was never awaited" when tests only inspect calls.
        if asyncio.iscoroutine(coro):
            coro.close()

    def delayed_performance_check(self, uri: str, delay: int) -> Any:
        self.delayed_calls.append((uri, delay))

        async def _check() -> Tuple[str, int]:
            return (uri, delay)

        return _check()


def _make_ports(
    *,
    ab_suffix: str = "",
    quality_gate_regen_mode: bool = False,
    prompt: Optional[Any] = None,
    scheduler: Optional[FakeScheduler] = None,
) -> tuple[ContentPorts, Any, FakeScheduler]:
    prompt_port = prompt or FakePromptContext(
        ab_suffix=ab_suffix,
        quality_gate_regen_mode=quality_gate_regen_mode,
    )
    sched = scheduler or FakeScheduler()
    ports = ContentPorts(prompt=prompt_port, scheduler=sched)
    return ports, prompt_port, sched


# --- Port helpers ---


class TestContentPortHelpers(unittest.TestCase):
    def test_prompt_context_view_defaults(self):
        view = PromptContextView()
        self.assertEqual(view.ab_suffix, "")
        self.assertFalse(view.quality_gate_regen_mode)

    def test_live_prompt_context_re_resolves(self):
        state = {"suffix": "A", "regen": False}

        live = LivePromptContext(
            _get_ab_suffix=lambda: state["suffix"],
            _get_quality_gate_regen_mode=lambda: state["regen"],
        )
        self.assertEqual(live.ab_suffix, "A")
        self.assertFalse(live.quality_gate_regen_mode)

        state["suffix"] = "\n\nB"
        state["regen"] = True
        self.assertEqual(live.ab_suffix, "\n\nB")
        self.assertTrue(live.quality_gate_regen_mode)

    def test_live_background_scheduler_delegates(self):
        spawned: List[Any] = []
        delayed: List[Tuple[str, int]] = []

        def _delayed(uri: str, delay: int):
            delayed.append((uri, delay))

            async def _inner():
                return None

            return _inner()

        def _spawn(coro: Any) -> None:
            spawned.append(coro)
            if asyncio.iscoroutine(coro):
                coro.close()

        live = LiveBackgroundScheduler(
            _spawn=_spawn,
            _delayed_performance_check=_delayed,
        )
        coro = live.delayed_performance_check("at://p", 3600)
        live.spawn(coro)
        self.assertEqual(len(spawned), 1)
        self.assertEqual(delayed, [("at://p", 3600)])


# --- No .bot on ContentService ---


class TestContentServiceNoBotAttr(unittest.TestCase):
    def test_service_source_has_no_bot_attribute(self):
        self.assertTrue(SERVICE_MODULE_PATH.is_file(), f"missing {SERVICE_MODULE_PATH}")
        source = SERVICE_MODULE_PATH.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(SERVICE_MODULE_PATH))

        bot_attrs: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "bot":
                bot_attrs.append(f"line {node.lineno}")
            if isinstance(node, ast.Name) and node.id == "bot":
                bot_attrs.append(f"name bot line {node.lineno}")

        self.assertEqual(
            bot_attrs,
            [],
            f"ContentService must not reference .bot / bot: {bot_attrs}",
        )
        self.assertNotIn("self.bot", source)
        self.assertIn("self._ports", source)

    def test_constructor_takes_ports_not_bot(self):
        ports, *_ = _make_ports()
        svc = ContentService(ports)
        self.assertFalse(hasattr(svc, "bot"))
        self.assertIs(svc._ports, ports)
        self.assertIsInstance(svc._ports, ContentPorts)


# --- build_structured_prompt ---


class TestBuildStructuredPrompt(unittest.TestCase):
    def test_appends_ab_suffix_when_present(self):
        ports, prompt, _ = _make_ports(ab_suffix="\n\n[AB:variant]")
        svc = ContentService(ports)

        result = svc.build_structured_prompt("Hello topic")

        self.assertTrue(result.startswith("Hello topic\n\n[AB:variant]"))
        self.assertIn(STRICT_CONTRACT_MARKER, result)
        self.assertGreaterEqual(prompt.ab_suffix_reads, 1)
        self.assertNotIn(REGEN_MARKER, result)

    def test_skips_empty_ab_suffix(self):
        ports, prompt, _ = _make_ports(ab_suffix="")
        svc = ContentService(ports)

        result = svc.build_structured_prompt("Base prompt")

        # No AB block between base and contract — contract follows base after rstrip.
        self.assertTrue(result.startswith("Base prompt\n\n" + STRICT_CONTRACT_MARKER))
        self.assertGreaterEqual(prompt.ab_suffix_reads, 1)

    def test_appends_regen_block_when_quality_gate_regen_mode(self):
        ports, prompt, _ = _make_ports(quality_gate_regen_mode=True)
        svc = ContentService(ports)

        result = svc.build_structured_prompt("Regen me")

        self.assertIn(STRICT_CONTRACT_MARKER, result)
        self.assertIn(REGEN_MARKER, result)
        self.assertGreaterEqual(prompt.regen_reads, 1)

    def test_no_regen_block_when_flag_false(self):
        ports, prompt, _ = _make_ports(quality_gate_regen_mode=False)
        svc = ContentService(ports)

        result = svc.build_structured_prompt("Plain")

        self.assertIn(STRICT_CONTRACT_MARKER, result)
        self.assertNotIn(REGEN_MARKER, result)
        self.assertGreaterEqual(prompt.regen_reads, 1)

    def test_ab_suffix_and_regen_together_via_prompt_context_view(self):
        """Frozen PromptContextView also satisfies PromptContextPort."""
        ports = ContentPorts(
            prompt=PromptContextView(
                ab_suffix="\n\nSUFFIX",
                quality_gate_regen_mode=True,
            ),
            scheduler=FakeScheduler(),
        )
        svc = ContentService(ports)

        result = svc.build_structured_prompt("  padded  ")

        self.assertIn("padded\n\nSUFFIX", result)
        self.assertIn(STRICT_CONTRACT_MARKER, result)
        self.assertIn(REGEN_MARKER, result)


# --- schedule_post_performance_checks ---


class TestSchedulePostPerformanceChecks(unittest.TestCase):
    def test_spawns_delayed_checks_for_canonical_delays(self):
        ports, _, sched = _make_ports()
        svc = ContentService(ports)
        uri = "at://did:plc:x/app.bsky.feed.post/abc"

        svc.schedule_post_performance_checks(uri)

        self.assertEqual(sched.delayed_calls, [(uri, d) for d in PERF_CHECK_DELAYS])
        self.assertEqual(len(sched.spawn_coros), len(PERF_CHECK_DELAYS))
        self.assertEqual(
            [delay for _, delay in sched.delayed_calls],
            list(PERF_CHECK_DELAYS),
        )


# --- prepare_outbound_text (thin port-path smoke) ---


class TestPrepareOutboundViaPorts(unittest.TestCase):
    def test_prepare_outbound_text_happy_and_empty(self):
        ports, *_ = _make_ports()
        svc = ContentService(ports)

        self.assertEqual(svc.prepare_outbound_text("ok post"), "ok post")
        with self.assertRaises(OutboundContentError):
            svc.prepare_outbound_text("   ")


if __name__ == "__main__":
    os.chdir(REPO_ROOT)
    unittest.main(verbosity=2)
