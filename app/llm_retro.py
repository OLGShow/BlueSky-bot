"""Weekly LLM reflection over policy-learner stats (PLRN-021).

Proposes allowlisted ``learning_parameters`` tweaks only — never arbitrary
bot_config rewrites. Apply via ``.bak`` + ``AtomicConfigWriter``.

Pure module: no ``bluesky_bot_v2`` import.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

try:
    from state_service import AtomicConfigWriter
except ImportError:  # pragma: no cover - optional at import time
    AtomicConfigWriter = None  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)

ALLOWLIST_KEYS = {
    "reward_scale",
    "epsilon",
    "max_arm_share_24h",
    "novelty_bonus",
    "novelty_idle_days",
    "decay_rate",
    "followers_reward_weight",
    "credit_weight_6h",
    "credit_weight_24h",
    "weight_min",
}

# Sensible min/max per key (inclusive).
BOUNDS: dict[str, tuple[float, float]] = {
    "reward_scale": (1.0, 50.0),
    "epsilon": (0.0, 0.5),
    "max_arm_share_24h": (0.10, 0.80),
    "novelty_bonus": (0.0, 0.5),
    "novelty_idle_days": (1.0, 90.0),
    "decay_rate": (0.0, 0.05),
    "followers_reward_weight": (0.0, 1.0),
    "credit_weight_6h": (0.0, 1.0),
    "credit_weight_24h": (0.0, 1.0),
    "weight_min": (0.01, 0.30),
}

GenerateJsonFn = Callable[[str], Awaitable[dict]]


def _utc_now(now: Optional[datetime] = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _clamp(key: str, value: Any) -> Optional[float]:
    """Coerce to float and clamp to BOUNDS; None if not numeric."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num != num:  # NaN
        return None
    lo, hi = BOUNDS[key]
    if num < lo:
        num = lo
    elif num > hi:
        num = hi
    if key == "novelty_idle_days":
        return float(int(round(num)))
    return num


def _extract_candidate(llm_json: dict) -> dict:
    """Prefer nested patch / learning_parameters; else treat top-level as patch."""
    if not isinstance(llm_json, dict):
        return {}
    for nest_key in ("learning_parameters", "patch", "tweaks", "params"):
        nested = llm_json.get(nest_key)
        if isinstance(nested, dict):
            return nested
    return llm_json


class LlmRetro:
    """Weekly LLM-driven allowlisted learning_parameters reflection."""

    def __init__(
        self,
        state_path: str = "learning_retro_state.json",
        report_dir: str = "reports",
        dry_run: bool = False,
    ) -> None:
        self.state_path = str(state_path)
        self.report_dir = str(report_dir)
        self.dry_run = bool(dry_run)

    def _load_state(self) -> dict[str, Any]:
        if not os.path.isfile(self.state_path):
            return {}
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("llm_retro state load failed: %s", exc)
            return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        parent = os.path.dirname(os.path.abspath(self.state_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = self.state_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(state, handle, indent=2, ensure_ascii=False, default=str)
            os.replace(tmp, self.state_path)
        except OSError as exc:
            logger.warning("llm_retro state save failed: %s", exc)
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    def should_run(
        self,
        now: Optional[datetime] = None,
        interval_days: int = 7,
    ) -> bool:
        """True if never ran, or last run is older than ``interval_days``."""
        now_utc = _utc_now(now)
        state = self._load_state()
        last = _parse_iso(state.get("last_ran") or state.get("last_run_at"))
        if last is None:
            return True
        interval = max(1, int(interval_days))
        return now_utc >= last + timedelta(days=interval)

    def mark_ran(self, now: Optional[datetime] = None) -> None:
        now_utc = _utc_now(now)
        state = self._load_state()
        state["last_ran"] = now_utc.isoformat()
        self._save_state(state)

    def build_prompt(
        self,
        learner_report: dict,
        recent_decisions: list[dict],
    ) -> str:
        allow = sorted(ALLOWLIST_KEYS)
        bounds_lines = "\n".join(
            f"  - {k}: [{BOUNDS[k][0]}, {BOUNDS[k][1]}]" for k in allow
        )
        report_json = json.dumps(learner_report or {}, ensure_ascii=False, default=str)
        # Cap decision payload size for the prompt
        decisions = list(recent_decisions or [])[-50:]
        decisions_json = json.dumps(decisions, ensure_ascii=False, default=str)
        return (
            "You are a bandit/policy-learning advisor for a social media bot.\n"
            "Propose small safe tweaks to learning_parameters ONLY.\n"
            "Return a single JSON object with key \"learning_parameters\" whose "
            "value is an object of proposed numeric changes.\n"
            "Only include keys you want to change. Unknown keys are rejected.\n\n"
            f"Allowlisted keys and bounds:\n{bounds_lines}\n\n"
            "Rules:\n"
            "- Prefer tiny adjustments (do not jump to extremes).\n"
            "- Keep credit_weight_6h + credit_weight_24h roughly summing near 1.0 "
            "if you change either.\n"
            "- If data is insufficient or performance looks healthy, return "
            '{"learning_parameters": {}}.\n'
            "- JSON only. No markdown fences.\n\n"
            f"Learner report:\n{report_json}\n\n"
            f"Recent decisions (up to 50):\n{decisions_json}\n"
        )

    def parse_and_validate(self, llm_json: dict) -> dict:
        """Return allowlisted+bounded patch; drop unknown / non-numeric keys."""
        candidate = _extract_candidate(llm_json if isinstance(llm_json, dict) else {})
        patch: dict[str, float] = {}
        for key, raw in candidate.items():
            if key not in ALLOWLIST_KEYS:
                continue
            clamped = _clamp(key, raw)
            if clamped is None:
                continue
            patch[key] = clamped
        return patch

    def apply_patch(self, config_path: str, patch: dict) -> bool:
        """Merge ``patch`` into ``learning_parameters`` only; bak + atomic write."""
        if not patch:
            return False
        path = str(config_path)
        config: dict[str, Any] = {}
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    loaded = json.load(handle)
                if isinstance(loaded, dict):
                    config = loaded
            except (OSError, json.JSONDecodeError) as exc:
                logger.error("llm_retro apply_patch load failed: %s", exc)
                return False

        lp = config.get("learning_parameters")
        if not isinstance(lp, dict):
            lp = {}
            config["learning_parameters"] = lp

        validated = self.parse_and_validate(patch)
        if not validated:
            return False

        for key, value in validated.items():
            lp[key] = value

        bak = path + ".bak"
        try:
            if os.path.isfile(path):
                shutil.copy2(path, bak)
            if AtomicConfigWriter is not None:
                AtomicConfigWriter.save(config, path)
            else:
                parent = os.path.dirname(os.path.abspath(path)) or "."
                os.makedirs(parent, exist_ok=True)
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as handle:
                    json.dump(config, handle, indent=2, ensure_ascii=False, default=str)
                os.replace(tmp, path)
        except OSError as exc:
            logger.error("llm_retro apply_patch write failed: %s", exc)
            return False
        return True

    def write_suggestion_report(
        self,
        patch: dict,
        raw: Any = None,
        applied: bool = False,
        now: Optional[datetime] = None,
    ) -> str:
        """Write ``reports/retro_YYYY-MM-DD.json``; return path written."""
        now_utc = _utc_now(now)
        day = now_utc.date().isoformat()
        os.makedirs(self.report_dir, exist_ok=True)
        out_path = os.path.join(self.report_dir, f"retro_{day}.json")
        payload = {
            "date": day,
            "generated_at": now_utc.isoformat(),
            "patch": patch if isinstance(patch, dict) else {},
            "raw": raw,
            "applied": bool(applied),
            "dry_run": self.dry_run,
        }
        try:
            if AtomicConfigWriter is not None:
                AtomicConfigWriter.save(payload, out_path)
            else:
                with open(out_path, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
        except OSError as exc:
            logger.warning("llm_retro report write failed: %s", exc)
        return out_path

    async def propose(
        self,
        generate_json_fn: GenerateJsonFn,
        report: dict,
        decisions: list[dict],
    ) -> dict:
        """Build prompt → LLM JSON → validated patch. Empty on failure."""
        prompt = self.build_prompt(report, decisions)
        try:
            llm_json = await generate_json_fn(prompt)
        except Exception as exc:
            logger.warning("llm_retro propose LLM call failed: %s", exc)
            return {}
        if not llm_json or not isinstance(llm_json, dict):
            return {}
        return self.parse_and_validate(llm_json)
