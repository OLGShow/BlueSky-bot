"""Follower cohort / returners analytics (Wave 1.1 / W1-005).

Pure set-diff math + durable state for ``learning_followers_cohort.json``.
Does **not** import ``bluesky_bot_v2``.

Rate-limit design
-----------------
Two representation modes for the stored ID sets:

* ``full`` — store raw DIDs (``did:plc:…``). Accurate; state grows with
  follower count.
* ``hash_bucket`` — store a compact hex digest per DID (truncated SHA-256).
  Same set algebra for new/returned/churned, smaller on disk, no PII-ish
  DID strings in state. Optional ``bucket_count`` documents a future
  sampling strategy (track only ``hash(did) % N == k``); W1-005 stores the
  full compact set when a snapshot is supplied.

Fetch / pagination / backoff live on the bot (W1-006): hard page limit,
``_atproto_execute`` retries, rare cadence via ``follower_analytics.every_n_cycles``.
This module stays pure math + state + daily report write helper.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Union

# ---------------------------------------------------------------------------
# Constants / schema
# ---------------------------------------------------------------------------

DEFAULT_STATE_PATH = "learning_followers_cohort.json"
DEFAULT_REPORTS_DIR = "reports"
STATE_VERSION = 1

MODE_FULL = "full"
MODE_HASH_BUCKET = "hash_bucket"
VALID_MODES = frozenset({MODE_FULL, MODE_HASH_BUCKET})

# Compact ID length for hash_bucket (hex chars of SHA-256).
DEFAULT_HASH_HEX_LEN = 16
# Documented sampling modulus (not applied unless caller filters DIDs first).
DEFAULT_BUCKET_COUNT = 256

MAX_HISTORY = 90
DEFAULT_SAMPLE_SIZE = 20
MAX_EVER_SEEN = 100_000

# Config defaults for bot wiring (W1-006).
DEFAULT_EVERY_N_CYCLES = 50
DEFAULT_MAX_PAGES = 8
DEFAULT_PAGE_SIZE = 100

IdSet = set[str]
StateDict = dict[str, Any]
ReportDict = dict[str, Any]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json_write(path: str, data: Mapping[str, Any]) -> None:
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


def hash_did(did: str, *, hex_len: int = DEFAULT_HASH_HEX_LEN) -> str:
    """Compact stable id for ``hash_bucket`` mode (truncated SHA-256 hex)."""
    digest = hashlib.sha256(str(did).encode("utf-8")).hexdigest()
    n = max(8, min(int(hex_len), 64))
    return digest[:n]


def bucket_index(did: str, bucket_count: int = DEFAULT_BUCKET_COUNT) -> int:
    """Which sampling bucket a DID falls into (for rate-limit paging later)."""
    n = max(1, int(bucket_count))
    digest = hashlib.sha256(str(did).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % n


def normalize_id(
    did: str,
    mode: str = MODE_FULL,
    *,
    hash_hex_len: int = DEFAULT_HASH_HEX_LEN,
) -> str:
    """Map a raw DID to the storage id for the given representation mode."""
    raw = str(did).strip()
    if not raw:
        return ""
    if mode == MODE_HASH_BUCKET:
        return hash_did(raw, hex_len=hash_hex_len)
    return raw


def to_id_set(
    dids: Iterable[str],
    mode: str = MODE_FULL,
    *,
    hash_hex_len: int = DEFAULT_HASH_HEX_LEN,
) -> IdSet:
    """Normalize an iterable of DIDs into a set of storage ids."""
    out: IdSet = set()
    for did in dids:
        nid = normalize_id(did, mode, hash_hex_len=hash_hex_len)
        if nid:
            out.add(nid)
    return out


def empty_state(
    mode: str = MODE_FULL,
    *,
    hash_hex_len: int = DEFAULT_HASH_HEX_LEN,
    bucket_count: int = DEFAULT_BUCKET_COUNT,
) -> StateDict:
    """Return a fresh cohort state document (schema v1)."""
    if mode not in VALID_MODES:
        raise ValueError(f"unsupported cohort mode: {mode!r}")
    return {
        "version": STATE_VERSION,
        "mode": mode,
        "hash_hex_len": int(hash_hex_len),
        "bucket_count": int(bucket_count),
        "updated_at": None,
        # Previous snapshot membership (storage ids).
        "prev": [],
        # Union of all ids ever observed (for returner detection).
        "ever_seen": [],
        # Optional explicit churned pool (mirrors ever_seen ∩ historically removed).
        "churned_history": [],
        # Rolling classification history (daily-ish reports).
        "history": [],
    }


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if item is None:
            continue
        s = str(item).strip()
        if s:
            out.append(s)
    return out


def normalize_state(raw: Optional[Mapping[str, Any]] = None) -> StateDict:
    """Coerce arbitrary JSON into a valid state dict (tolerant load)."""
    if not isinstance(raw, Mapping):
        return empty_state()
    mode = str(raw.get("mode") or MODE_FULL)
    if mode not in VALID_MODES:
        mode = MODE_FULL
    try:
        hex_len = int(raw.get("hash_hex_len") or DEFAULT_HASH_HEX_LEN)
    except (TypeError, ValueError):
        hex_len = DEFAULT_HASH_HEX_LEN
    try:
        bucket_count = int(raw.get("bucket_count") or DEFAULT_BUCKET_COUNT)
    except (TypeError, ValueError):
        bucket_count = DEFAULT_BUCKET_COUNT

    state = empty_state(mode, hash_hex_len=hex_len, bucket_count=bucket_count)
    state["version"] = int(raw.get("version") or STATE_VERSION)
    state["updated_at"] = raw.get("updated_at")
    state["prev"] = _as_str_list(raw.get("prev"))
    state["ever_seen"] = _as_str_list(raw.get("ever_seen"))
    state["churned_history"] = _as_str_list(raw.get("churned_history"))
    history = raw.get("history")
    if isinstance(history, list):
        cleaned: list[dict[str, Any]] = []
        for item in history:
            if isinstance(item, dict):
                cleaned.append(dict(item))
        state["history"] = cleaned[-MAX_HISTORY:]
    return state


def load_state(path: Union[str, Path] = DEFAULT_STATE_PATH) -> StateDict:
    """Load cohort state from disk; missing/corrupt → empty state."""
    state_path = Path(path)
    if not state_path.is_file():
        return empty_state()
    try:
        with open(state_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return empty_state()
    return normalize_state(data if isinstance(data, dict) else None)


def save_state(path: Union[str, Path], state: Mapping[str, Any]) -> None:
    """Persist cohort state atomically."""
    normalized = normalize_state(state)
    _atomic_json_write(str(path), normalized)


def serialize_state(state: Mapping[str, Any]) -> StateDict:
    """Stable JSON-ready copy (lists sorted for deterministic dumps)."""
    normalized = normalize_state(state)
    return {
        "version": normalized["version"],
        "mode": normalized["mode"],
        "hash_hex_len": normalized["hash_hex_len"],
        "bucket_count": normalized["bucket_count"],
        "updated_at": normalized.get("updated_at"),
        "prev": sorted(normalized["prev"]),
        "ever_seen": sorted(normalized["ever_seen"]),
        "churned_history": sorted(normalized["churned_history"]),
        "history": list(normalized.get("history") or []),
    }


# ---------------------------------------------------------------------------
# Cohort math
# ---------------------------------------------------------------------------


def diff_cohorts(
    prev: set[str],
    curr: set[str],
    *,
    ever_seen: Optional[set[str]] = None,
) -> dict[str, set[str]]:
    """Classify membership change between two snapshots.

    Definitions (storage ids — DIDs or hashes):

    * **churned** — in ``prev``, not in ``curr``
    * **new** — in ``curr``, not in ``prev``, never seen before
    * **returned** — in ``curr``, not in ``prev``, but present in
      ``ever_seen`` (was observed in an earlier snapshot, then left)

    ``ever_seen`` should be the historical union of prior memberships
    (typically ``state["ever_seen"]`` before applying ``curr``). If omitted
    or empty, every addition is classified as ``new`` (no returners).

    Returns dict with keys ``new``, ``returned``, ``churned`` (each a set).
    """
    prev_s = set(prev) if prev else set()
    curr_s = set(curr) if curr else set()
    seen = set(ever_seen) if ever_seen else set()

    added = curr_s - prev_s
    churned = prev_s - curr_s
    returned = added & seen
    new = added - seen
    return {
        "new": new,
        "returned": returned,
        "churned": churned,
    }


def _sample(ids: Iterable[str], limit: int) -> list[str]:
    if limit <= 0:
        return []
    return sorted(ids)[: int(limit)]


def _trim_ever_seen(ever: IdSet, curr: IdSet, churned_hist: IdSet) -> IdSet:
    """Bound ``ever_seen`` growth while preferring current + churned_history."""
    if len(ever) <= MAX_EVER_SEEN:
        return ever
    keep = set(curr) | set(churned_hist)
    # Fill remaining slots from the rest of ever_seen (stable order).
    remaining = sorted(ever - keep)
    room = max(0, MAX_EVER_SEEN - len(keep))
    keep.update(remaining[:room])
    return keep


def apply_snapshot(
    state: Optional[Mapping[str, Any]],
    current_dids: Iterable[str],
    ts: Optional[str] = None,
    *,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
) -> tuple[StateDict, ReportDict]:
    """Apply a follower-id snapshot; return updated state + daily report fields.

    Parameters
    ----------
    state:
        Prior cohort state (or None / empty → first snapshot).
    current_dids:
        Iterable of raw DIDs for the *current* snapshot. Representation is
        chosen from ``state["mode"]`` (full vs hash_bucket).
    ts:
        ISO timestamp for the report row; defaults to UTC now.
    sample_size:
        Max ids to include per class in ``*_sample`` report fields.

    Returns
    -------
    (state, report_dict)
        ``report_dict`` includes counts ``new`` / ``returned`` / ``churned``,
        sizes, optional samples, and ``ts`` — suitable for
        ``reports/followers_daily_YYYY-MM-DD.json`` (written by W1-006).
    """
    st = normalize_state(state)
    mode = st["mode"]
    hex_len = int(st["hash_hex_len"])
    stamp = ts if ts is not None else _utc_now_iso()

    curr = to_id_set(current_dids, mode, hash_hex_len=hex_len)
    prev = set(st["prev"])
    ever_seen = set(st["ever_seen"])
    churned_hist = set(st["churned_history"])

    # First snapshot: establish baseline without classifying everyone as new.
    if not prev and not ever_seen:
        st["prev"] = sorted(curr)
        st["ever_seen"] = sorted(curr)
        st["churned_history"] = []
        st["updated_at"] = stamp
        report: ReportDict = {
            "ts": stamp,
            "mode": mode,
            "baseline": True,
            "new": 0,
            "returned": 0,
            "churned": 0,
            "curr_size": len(curr),
            "prev_size": 0,
            "net": len(curr),
            "new_sample": [],
            "returned_sample": [],
            "churned_sample": [],
        }
        history = list(st.get("history") or [])
        history.append(
            {
                "ts": stamp,
                "new": 0,
                "returned": 0,
                "churned": 0,
                "curr_size": len(curr),
                "baseline": True,
            }
        )
        st["history"] = history[-MAX_HISTORY:]
        return st, report

    classes = diff_cohorts(prev, curr, ever_seen=ever_seen)
    new_ids = classes["new"]
    returned_ids = classes["returned"]
    churned_ids = classes["churned"]

    ever_seen |= curr
    churned_hist |= churned_ids
    # Drop from churned_history anyone who returned / is currently following.
    churned_hist -= curr
    ever_seen = _trim_ever_seen(ever_seen, curr, churned_hist)
    if len(churned_hist) > MAX_EVER_SEEN:
        churned_hist = set(sorted(churned_hist)[:MAX_EVER_SEEN])

    st["prev"] = sorted(curr)
    st["ever_seen"] = sorted(ever_seen)
    st["churned_history"] = sorted(churned_hist)
    st["updated_at"] = stamp

    report = {
        "ts": stamp,
        "mode": mode,
        "baseline": False,
        "new": len(new_ids),
        "returned": len(returned_ids),
        "churned": len(churned_ids),
        "curr_size": len(curr),
        "prev_size": len(prev),
        "net": len(curr) - len(prev),
        "new_sample": _sample(new_ids, sample_size),
        "returned_sample": _sample(returned_ids, sample_size),
        "churned_sample": _sample(churned_ids, sample_size),
    }

    history = list(st.get("history") or [])
    history.append(
        {
            "ts": stamp,
            "new": report["new"],
            "returned": report["returned"],
            "churned": report["churned"],
            "curr_size": report["curr_size"],
            "net": report["net"],
            "new_sample": report["new_sample"],
            "returned_sample": report["returned_sample"],
            "churned_sample": report["churned_sample"],
        }
    )
    st["history"] = history[-MAX_HISTORY:]
    return st, report


def followers_daily_report_path(
    ts: Optional[str] = None,
    *,
    out_dir: Union[str, Path] = DEFAULT_REPORTS_DIR,
) -> Path:
    """Path for ``reports/followers_daily_YYYY-MM-DD.json`` (UTC day)."""
    if ts:
        try:
            day = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if day.tzinfo is None:
                day = day.replace(tzinfo=timezone.utc)
            day_s = day.astimezone(timezone.utc).strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            day_s = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    else:
        day_s = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Path(out_dir) / f"followers_daily_{day_s}.json"


def write_followers_daily_report(
    report: Mapping[str, Any],
    *,
    out_dir: Union[str, Path] = DEFAULT_REPORTS_DIR,
) -> Path:
    """Persist cohort ``apply_snapshot`` report as followers_daily_*.json."""
    path = followers_daily_report_path(
        report.get("ts") if isinstance(report, Mapping) else None,
        out_dir=out_dir,
    )
    payload = dict(report) if isinstance(report, Mapping) else {"report": report}
    payload.setdefault("date", path.stem.replace("followers_daily_", "", 1))
    _atomic_json_write(str(path), payload)
    return path


def parse_follower_analytics_config(
    raw: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Normalize ``bot_config.follower_analytics`` knobs."""
    cfg = raw if isinstance(raw, Mapping) else {}
    mode = str(cfg.get("mode") or MODE_FULL).strip() or MODE_FULL
    if mode not in VALID_MODES:
        mode = MODE_FULL
    try:
        every_n = max(1, int(cfg.get("every_n_cycles", DEFAULT_EVERY_N_CYCLES)))
    except (TypeError, ValueError):
        every_n = DEFAULT_EVERY_N_CYCLES
    try:
        max_pages = max(1, min(20, int(cfg.get("max_pages", DEFAULT_MAX_PAGES))))
    except (TypeError, ValueError):
        max_pages = DEFAULT_MAX_PAGES
    try:
        page_size = max(1, min(100, int(cfg.get("page_size", DEFAULT_PAGE_SIZE))))
    except (TypeError, ValueError):
        page_size = DEFAULT_PAGE_SIZE
    state_path = str(cfg.get("state_path") or DEFAULT_STATE_PATH).strip()
    reports_dir = str(cfg.get("reports_dir") or DEFAULT_REPORTS_DIR).strip()
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "every_n_cycles": every_n,
        "max_pages": max_pages,
        "page_size": page_size,
        "mode": mode,
        "state_path": state_path or DEFAULT_STATE_PATH,
        "reports_dir": reports_dir or DEFAULT_REPORTS_DIR,
    }


class FollowerCohortTracker:
    """Thin persistence wrapper around :func:`apply_snapshot`.

    Network fetch lives on the bot (W1-006). Call :meth:`apply` with an
    already-collected id iterable.
    """

    def __init__(
        self,
        path: str = DEFAULT_STATE_PATH,
        *,
        mode: str = MODE_FULL,
        hash_hex_len: int = DEFAULT_HASH_HEX_LEN,
        bucket_count: int = DEFAULT_BUCKET_COUNT,
    ):
        self.path = str(path)
        self._default_mode = mode
        self._hash_hex_len = hash_hex_len
        self._bucket_count = bucket_count
        self.state: StateDict = empty_state(
            mode,
            hash_hex_len=hash_hex_len,
            bucket_count=bucket_count,
        )
        self.load()

    def load(self) -> None:
        loaded = load_state(self.path)
        if not Path(self.path).is_file():
            self.state = empty_state(
                self._default_mode,
                hash_hex_len=self._hash_hex_len,
                bucket_count=self._bucket_count,
            )
        else:
            self.state = loaded

    def save(self) -> None:
        save_state(self.path, self.state)

    def apply(
        self,
        current_dids: Iterable[str],
        ts: Optional[str] = None,
        *,
        sample_size: int = DEFAULT_SAMPLE_SIZE,
        persist: bool = True,
    ) -> ReportDict:
        """Apply snapshot, update in-memory state, optionally persist."""
        self.state, report = apply_snapshot(
            self.state,
            current_dids,
            ts,
            sample_size=sample_size,
        )
        if persist:
            self.save()
        return report
