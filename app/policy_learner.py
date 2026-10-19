"""Thompson-sampling policy learner (Beta bandit) for strategy arms.

Pure module: no bluesky_bot_v2 import. State persists to learning_state.json.
"""

from __future__ import annotations

import json
import math
import os
import random
import shutil
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

try:
    from state_service import AtomicConfigWriter
except ImportError:  # pragma: no cover - optional at import time
    AtomicConfigWriter = None  # type: ignore[misc, assignment]

DEFAULT_PARAMS: dict[str, Any] = {
    "reward_scale": 10,
    "credit_weight_6h": 0.35,
    "credit_weight_24h": 0.65,
    "min_settled_posts": 5,
    "max_arm_share_24h": 0.40,
    "novelty_idle_days": 14,
    "novelty_bonus": 0.15,
    "epsilon": 0.10,
    "decay_every_cycles": 20,
    "decay_rate": 0.005,
    "weight_min": 0.05,
    "warm_start_strength": 4,
    "deltas_max": 20,
    "report_path": "reports/learning_report.json",
    "followers_reward_weight": 0.0,
    "followers_scale": 5.0,
    "followers_state_path": "learning_followers.json",
}

CREDIT_WEIGHTS = {
    "6h": "credit_weight_6h",
    "24h": "credit_weight_24h",
}


def compute_reward(
    likes: float,
    replies: float,
    reposts: float,
    reward_scale: float = 10,
    followers_delta: float | None = None,
    followers_weight: float = 0.0,
    followers_scale: float = 5.0,
) -> float:
    """Map engagement (+ optional followers delta) to reward in [0, 1)."""
    score = float(likes) + 2.0 * float(replies) + 3.0 * float(reposts)
    scale = float(reward_scale) if reward_scale else 10.0
    if scale <= 0:
        scale = 10.0
    eng = 1.0 - math.exp(-score / scale)
    if followers_weight <= 0 or followers_delta is None:
        return eng
    f_scale = float(followers_scale) if followers_scale else 5.0
    if f_scale <= 0:
        f_scale = 5.0
    # Clamp delta for stability; positive growth helps.
    d = max(-f_scale * 3, min(f_scale * 3, float(followers_delta)))
    if d >= 0:
        r_f = 1.0 - math.exp(-d / f_scale)
    else:
        r_f = -(1.0 - math.exp(d / f_scale))  # negative in (-1, 0]
    w = min(1.0, max(0.0, float(followers_weight)))
    blended = (1.0 - w) * eng + w * ((r_f + 1.0) / 2.0)
    return max(0.0, min(0.999999, blended))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _coerce_post_timestamp(value: Any) -> Optional[datetime]:
    """Parse created_at/timestamp from memory posts (datetime or ISO str)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return _parse_iso(value)
    return None


FORMAT_ARM_KEYS = ("format_a", "format_b")


def recent_arm_keys_24h(
    posts,
    field: str,
    *,
    now: Optional[datetime] = None,
    hours: float = 24,
) -> list[str]:
    """Arm keys from ``posts[*][field]`` with a timestamp inside the last ``hours``."""
    ref = now if now is not None else datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    cutoff = ref - timedelta(hours=float(hours))
    keys: list[str] = []
    for post in posts or []:
        if not isinstance(post, dict):
            continue
        sk = post.get(field)
        if not sk:
            continue
        ts = _coerce_post_timestamp(post.get("created_at"))
        if ts is None:
            ts = _coerce_post_timestamp(post.get("timestamp"))
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts >= cutoff:
            keys.append(str(sk))
    return keys


def recent_strategy_keys_24h(
    posts,
    *,
    now: Optional[datetime] = None,
    hours: float = 24,
) -> list[str]:
    """Strategy keys from posts with a timestamp inside the last ``hours``."""
    return recent_arm_keys_24h(posts, "strategy_key", now=now, hours=hours)


def recent_format_keys_24h(
    posts,
    *,
    now: Optional[datetime] = None,
    hours: float = 24,
) -> list[str]:
    """``ab_format`` keys from posts with a timestamp inside the last ``hours``."""
    return recent_arm_keys_24h(posts, "ab_format", now=now, hours=hours)


# Restart catch-up windows (hours): 6h∈[6,36); 24h∈[24,48)
CATCH_UP_6H_MIN_H = 6.0
CATCH_UP_6H_MAX_H = 36.0
CATCH_UP_24H_MIN_H = 24.0
CATCH_UP_24H_MAX_H = 48.0


def _catch_up_checks_for_age(
    age_hours: float,
    rewarded: list,
) -> list[str]:
    checks: list[str] = []
    if (
        CATCH_UP_6H_MIN_H <= age_hours < CATCH_UP_6H_MAX_H
        and "6h" not in rewarded
    ):
        checks.append("6h")
    if (
        CATCH_UP_24H_MIN_H <= age_hours < CATCH_UP_24H_MAX_H
        and "24h" not in rewarded
    ):
        checks.append("24h")
    return checks


def _post_age_hours(
    post: dict,
    now: Optional[datetime] = None,
) -> Optional[float]:
    ref = now if now is not None else datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)

    ts = _coerce_post_timestamp(post.get("created_at"))
    if ts is None:
        ts = _coerce_post_timestamp(post.get("timestamp"))
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    age_hours = (ref - ts).total_seconds() / 3600.0
    if age_hours < 0:
        return None
    return age_hours


def eligible_catch_up_checks(
    post: dict,
    now: Optional[datetime] = None,
) -> list[str]:
    """Return check_ids still due for restart catch-up credit.

    Eligibility: ``uri`` + ``strategy_key``, ``type != 'comment'``.
    Windows: ``6h`` when age∈[6h,36h); ``24h`` when age∈[24h,48h).
    Skips checks already present in ``rewarded_checks``.
    """
    if not isinstance(post, dict):
        return []
    if not post.get("uri") or not post.get("strategy_key"):
        return []
    if post.get("type") == "comment":
        return []

    age_hours = _post_age_hours(post, now)
    if age_hours is None:
        return []

    rewarded = post.get("rewarded_checks") or []
    if not isinstance(rewarded, list):
        rewarded = []

    return _catch_up_checks_for_age(age_hours, rewarded)


def eligible_format_catch_up_checks(
    post: dict,
    now: Optional[datetime] = None,
) -> list[str]:
    """Return format check_ids due for restart catch-up (FormatBandit).

    Eligibility: ``uri`` + ``ab_format``, ``type != 'comment'``.
    Same age windows as strategy catch-up; uses ``format_rewarded_checks``.
    """
    if not isinstance(post, dict):
        return []
    if not post.get("uri") or not post.get("ab_format"):
        return []
    if post.get("type") == "comment":
        return []

    age_hours = _post_age_hours(post, now)
    if age_hours is None:
        return []

    rewarded = post.get("format_rewarded_checks") or []
    if not isinstance(rewarded, list):
        rewarded = []

    return _catch_up_checks_for_age(age_hours, rewarded)


def _merge_params(params: Optional[dict]) -> dict[str, Any]:
    merged = dict(DEFAULT_PARAMS)
    if params:
        for key, value in params.items():
            if value is not None:
                merged[key] = value
    return merged


def _normalize_bootstrap(
    arm_keys: list[str],
    bootstrap_weights: Optional[dict],
) -> dict[str, float]:
    raw = dict(bootstrap_weights or {})
    weights: dict[str, float] = {}
    for key in arm_keys:
        weights[key] = float(raw.get(key, 0.0))
    total = sum(weights.values())
    if total <= 0 and arm_keys:
        even = 1.0 / len(arm_keys)
        return {k: even for k in arm_keys}
    if total <= 0:
        return {}
    return {k: v / total for k, v in weights.items()}


def _warm_start_arm(weight: float, strength: float) -> dict[str, Any]:
    w = max(0.0, min(1.0, float(weight)))
    s = float(strength)
    alpha = 1.0 + s * w
    beta = 1.0 + s * (1.0 - w)
    return {
        "alpha": alpha,
        "beta": beta,
        "prior_alpha": alpha,
        "prior_beta": beta,
        "trials": 0.0,
        "last_reward": None,
        "last_credit_at": None,
        "last_pick_at": None,
    }


def _atomic_json_write(path: str, data: dict) -> None:
    """Write JSON atomically; prefer AtomicConfigWriter when available."""
    if AtomicConfigWriter is not None:
        AtomicConfigWriter.save(data, path)
        return
    dir_name = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(dir_name, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False, default=str)
        shutil.move(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class PolicyLearner:
    """Beta-Thompson bandit over named strategy arms."""

    def __init__(
        self,
        path,
        params: dict,
        arm_keys: list[str],
        bootstrap_weights: dict,
    ):
        self.path = str(path)
        self.params = _merge_params(params)
        keys = list(arm_keys or [])
        self.bootstrap_weights = _normalize_bootstrap(keys, bootstrap_weights)
        self.version = 1
        self.cycle_count = 0
        self.total_credit_mass = 0.0
        self.arms: dict[str, dict[str, Any]] = {}
        self.retired_arms: dict[str, dict[str, Any]] = {}
        self.deltas: list[dict[str, Any]] = []
        self.last_pick_meta: Optional[dict[str, Any]] = None
        strength = float(self.params["warm_start_strength"])
        for key in keys:
            w = self.bootstrap_weights.get(key, 0.0)
            self.arms[key] = _warm_start_arm(w, strength)

    @classmethod
    def load(
        cls,
        path,
        params: dict,
        arm_keys: list[str],
        bootstrap_weights: dict,
    ) -> "PolicyLearner":
        """Load from disk if present; otherwise warm-start a fresh learner."""
        learner = cls(path, params, arm_keys, bootstrap_weights)
        state_path = Path(path)
        if not state_path.is_file():
            return learner
        try:
            with open(state_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return learner
        learner._apply_state(data)
        learner.sync_arms_with_config(arm_keys, bootstrap_weights)
        return learner

    def _apply_state(self, data: dict) -> None:
        self.version = int(data.get("version", 1))
        self.cycle_count = int(data.get("cycle_count", 0))
        self.total_credit_mass = float(data.get("total_credit_mass", 0.0))
        arms = data.get("arms") or {}
        if isinstance(arms, dict):
            self.arms = {str(k): dict(v) for k, v in arms.items() if isinstance(v, dict)}
        retired = data.get("retired_arms") or {}
        if isinstance(retired, dict):
            self.retired_arms = {
                str(k): dict(v) for k, v in retired.items() if isinstance(v, dict)
            }
        deltas = data.get("deltas") or []
        if isinstance(deltas, list):
            self.deltas = [dict(d) for d in deltas if isinstance(d, dict)]
        boot = data.get("bootstrap_weights")
        if isinstance(boot, dict) and boot:
            self.bootstrap_weights = {
                str(k): float(v) for k, v in boot.items()
            }

    def save(self) -> None:
        """Persist learning state atomically."""
        _atomic_json_write(self.path, self._to_state())

    def _to_state(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "cycle_count": self.cycle_count,
            "total_credit_mass": self.total_credit_mass,
            "arms": deepcopy(self.arms),
            "retired_arms": deepcopy(self.retired_arms),
            "deltas": list(self.deltas),
            "bootstrap_weights": dict(self.bootstrap_weights),
        }

    def _credit_weight(self, check_id: str) -> float:
        param_key = CREDIT_WEIGHTS.get(check_id)
        if param_key is None:
            return 0.0
        return float(self.params.get(param_key, 0.0))

    def _idle_days(self, arm: dict[str, Any]) -> float:
        candidates = [
            _parse_iso(arm.get("last_credit_at")),
            _parse_iso(arm.get("last_pick_at")),
        ]
        stamps = [ts for ts in candidates if ts is not None]
        if not stamps:
            return float("inf")
        latest = max(stamps)
        now = datetime.now(timezone.utc)
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)
        return max(0.0, (now - latest).total_seconds() / 86400.0)

    def _share_map(self, recent: list[str]) -> dict[str, float]:
        if not recent:
            return {}
        counts: dict[str, int] = {}
        for key in recent:
            counts[key] = counts.get(key, 0) + 1
        n = float(len(recent))
        return {k: c / n for k, c in counts.items()}

    def pick_arm(self, keys, recent_strategy_keys_24h: list[str]) -> str:
        """Thompson sample among keys; apply novelty, share cap, and ε-greedy.

        Sets ``last_pick_meta`` to ``{arm, reason}`` where reason is one of
        ``thompson``, ``epsilon``, or ``share_cap`` (all arms over share).
        """
        enabled = [k for k in (keys or []) if k in self.arms]
        if not enabled:
            raise ValueError("pick_arm: no known arms in keys")

        max_share = float(self.params["max_arm_share_24h"])
        shares = self._share_map(list(recent_strategy_keys_24h or []))
        candidates = [
            k for k in enabled if shares.get(k, 0.0) <= max_share
        ]
        share_fallback = False
        if not candidates:
            candidates = list(enabled)
            share_fallback = True

        epsilon = float(self.params["epsilon"])
        if random.random() < epsilon:
            chosen = random.choice(candidates)
            reason = "share_cap" if share_fallback else "epsilon"
            self.last_pick_meta = {"arm": chosen, "reason": reason}
            return chosen

        novelty_days = float(self.params["novelty_idle_days"])
        novelty_bonus = float(self.params["novelty_bonus"])
        best_key = candidates[0]
        best_sample = float("-inf")
        for key in candidates:
            arm = self.arms[key]
            alpha = max(1e-9, float(arm.get("alpha", 1.0)))
            beta = max(1e-9, float(arm.get("beta", 1.0)))
            sample = random.betavariate(alpha, beta)
            if self._idle_days(arm) >= novelty_days:
                sample += novelty_bonus
            if sample > best_sample:
                best_sample = sample
                best_key = key
        reason = "share_cap" if share_fallback else "thompson"
        self.last_pick_meta = {"arm": best_key, "reason": reason}
        return best_key

    def record_pick(self, strategy_key: str) -> None:
        """Stamp last_pick_at after a successful pick."""
        arm = self.arms.get(strategy_key)
        if arm is None:
            return
        arm["last_pick_at"] = _utc_now_iso()

    def credit(
        self,
        strategy_key: str,
        likes,
        reposts,
        replies,
        check_id: str,
        followers_delta=None,
    ) -> bool:
        """Apply fractional dual-credit. Returns False if arm unknown."""
        arm = self.arms.get(strategy_key)
        if arm is None:
            return False
        if likes is None or reposts is None or replies is None:
            return False
        w = self._credit_weight(check_id)
        if w <= 0:
            return False
        r = compute_reward(
            likes,
            replies,
            reposts,
            reward_scale=float(self.params["reward_scale"]),
            followers_delta=followers_delta,
            followers_weight=float(self.params.get("followers_reward_weight", 0.0)),
            followers_scale=float(self.params.get("followers_scale", 5.0)),
        )
        arm["alpha"] = float(arm.get("alpha", 1.0)) + w * r
        arm["beta"] = float(arm.get("beta", 1.0)) + w * (1.0 - r)
        arm["trials"] = float(arm.get("trials", 0.0)) + w
        arm["last_reward"] = r
        arm["last_credit_at"] = _utc_now_iso()
        self.total_credit_mass += w
        self._append_delta(
            {
                "ts": arm["last_credit_at"],
                "arm": strategy_key,
                "check": check_id,
                "r": r,
                "w": w,
                "alpha": arm["alpha"],
                "beta": arm["beta"],
            }
        )
        return True

    def _append_delta(self, entry: dict[str, Any]) -> None:
        max_n = int(self.params["deltas_max"])
        self.deltas.append(entry)
        if max_n > 0 and len(self.deltas) > max_n:
            self.deltas = self.deltas[-max_n:]

    def maybe_decay(self) -> None:
        """Increment cycle counter; soft-decay alphas/betas every N cycles."""
        self.cycle_count += 1
        every = int(self.params["decay_every_cycles"])
        if every <= 0 or self.cycle_count % every != 0:
            return
        rate = float(self.params["decay_rate"])
        keep = 1.0 - rate
        for arm in self.arms.values():
            prior_a = float(arm.get("prior_alpha", 1.0))
            prior_b = float(arm.get("prior_beta", 1.0))
            arm["alpha"] = keep * float(arm.get("alpha", 1.0)) + rate * prior_a
            arm["beta"] = keep * float(arm.get("beta", 1.0)) + rate * prior_b

    def export_weights(self) -> dict[str, float]:
        """Normalized means, or bootstrap while under min_settled_posts freeze."""
        min_settled = float(self.params["min_settled_posts"])
        if self.total_credit_mass < min_settled:
            if not self.arms:
                return {}
            boot = {
                k: float(self.bootstrap_weights.get(k, 0.0)) for k in self.arms
            }
            total = sum(boot.values())
            if total <= 0:
                even = 1.0 / len(self.arms)
                return {k: even for k in self.arms}
            return {k: v / total for k, v in boot.items()}

        weight_min = float(self.params["weight_min"])
        raw: dict[str, float] = {}
        for key, arm in self.arms.items():
            alpha = float(arm.get("alpha", 1.0))
            beta = float(arm.get("beta", 1.0))
            denom = alpha + beta
            mean = alpha / denom if denom > 0 else 0.5
            raw[key] = max(weight_min, mean)
        total = sum(raw.values())
        if total <= 0:
            even = 1.0 / len(raw) if raw else 0.0
            return {k: even for k in raw}
        return {k: v / total for k, v in raw.items()}

    def sync_arms_with_config(
        self,
        arm_keys: list[str],
        bootstrap: dict,
    ) -> None:
        """Add missing arms (warm-start); retire arms absent from config."""
        keys = list(arm_keys or [])
        self.bootstrap_weights = _normalize_bootstrap(keys, bootstrap)
        strength = float(self.params["warm_start_strength"])
        key_set = set(keys)

        for key in list(self.arms.keys()):
            if key not in key_set:
                arm = self.arms.pop(key)
                trials = float(arm.get("trials", 0.0))
                if trials > 0:
                    self.retired_arms[key] = arm

        for key in keys:
            if key in self.arms:
                continue
            if key in self.retired_arms:
                self.arms[key] = self.retired_arms.pop(key)
                continue
            w = self.bootstrap_weights.get(key, 0.0)
            self.arms[key] = _warm_start_arm(w, strength)

    def report(self) -> dict:
        """Observability snapshot for logging / JSON report.

        Per-arm: alpha, beta, mean, trials, last_reward (plus timestamps).
        Top-level: total_credit_mass, last_20_deltas, export_weights.
        """
        per_arm: dict[str, Any] = {}
        for key, arm in self.arms.items():
            alpha = float(arm.get("alpha", 1.0))
            beta = float(arm.get("beta", 1.0))
            denom = alpha + beta
            mean = alpha / denom if denom > 0 else 0.5
            per_arm[key] = {
                "alpha": alpha,
                "beta": beta,
                "mean": mean,
                "trials": float(arm.get("trials", 0.0)),
                "last_reward": arm.get("last_reward"),
                "last_credit_at": arm.get("last_credit_at"),
                "last_pick_at": arm.get("last_pick_at"),
            }
        return {
            "version": self.version,
            "cycle_count": self.cycle_count,
            "total_credit_mass": self.total_credit_mass,
            "arms": per_arm,
            "last_20_deltas": list(self.deltas[-20:]),
            "export_weights": self.export_weights(),
            "retired_arms": list(self.retired_arms.keys()),
        }

    def write_report(self, path: Optional[str] = None) -> str:
        """Write ``report()`` JSON; create parent dirs. Returns path written."""
        out = path or self.params.get("report_path") or DEFAULT_PARAMS["report_path"]
        out = str(out)
        parent = os.path.dirname(os.path.abspath(out))
        if parent:
            os.makedirs(parent, exist_ok=True)
        _atomic_json_write(out, self.report())
        return out

    def sync_config_weights(self, config_path) -> bool:
        """Write export_weights into post_strategies via bak + atomic save.

        Freeze guard: if total_credit_mass < min_settled_posts, skip write
        and return False. Otherwise `.bak` then AtomicConfigWriter; return True.
        """
        min_settled = float(self.params["min_settled_posts"])
        if self.total_credit_mass < min_settled:
            return False

        path = str(config_path)
        config: dict[str, Any] = {}
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                config = loaded
        bak = path + ".bak"
        if os.path.isfile(path):
            shutil.copy2(path, bak)
        config["post_strategies"] = self.export_weights()
        _atomic_json_write(path, config)
        return True
