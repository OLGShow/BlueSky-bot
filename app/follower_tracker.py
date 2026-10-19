"""Pure follower-count snapshot tracker for reward blending (PLRN-020).

No bluesky_bot_v2 import. State persists to learning_followers.json.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Union

MAX_SNAPSHOTS = 500


def delta_between(count_at_start, count_now) -> int:
    """Return integer followers delta: now - start."""
    return int(count_now) - int(count_at_start)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _atomic_json_write(path: str, data: dict) -> None:
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


class FollowerTracker:
    """Append-only follower count snapshots with bounded history."""

    def __init__(self, path: str = "learning_followers.json"):
        self.path = str(path)
        self.snapshots: list[dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        """Load snapshots from disk; ignore missing/corrupt files."""
        state_path = Path(self.path)
        if not state_path.is_file():
            self.snapshots = []
            return
        try:
            with open(state_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            self.snapshots = []
            return
        raw = data.get("snapshots") if isinstance(data, dict) else None
        if not isinstance(raw, list):
            self.snapshots = []
            return
        snaps: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            count = item.get("count")
            if count is None:
                continue
            try:
                snaps.append(
                    {
                        "ts": item.get("ts") or _utc_now_iso(),
                        "count": int(count),
                    }
                )
            except (TypeError, ValueError):
                continue
        self.snapshots = snaps[-MAX_SNAPSHOTS:]

    def save(self) -> None:
        """Persist snapshots atomically."""
        _atomic_json_write(
            self.path,
            {"version": 1, "snapshots": self.snapshots},
        )

    def record(self, count: int, ts: Optional[str] = None) -> None:
        """Append a snapshot and trim to ``MAX_SNAPSHOTS``."""
        self.snapshots.append(
            {
                "ts": ts if ts is not None else _utc_now_iso(),
                "count": int(count),
            }
        )
        if len(self.snapshots) > MAX_SNAPSHOTS:
            self.snapshots = self.snapshots[-MAX_SNAPSHOTS:]
        self.save()

    def latest(self) -> Optional[int]:
        """Return the most recent followers count, if any."""
        if not self.snapshots:
            return None
        return int(self.snapshots[-1]["count"])

    def delta_1h(self, *, now: Optional[datetime] = None) -> Optional[float]:
        """Followers change vs the last snapshot at or before ~1h ago.

        Returns ``None`` when history is insufficient (no baseline ≥1h old).
        """
        latest = self.latest()
        if latest is None:
            return None
        ref = now or datetime.now(timezone.utc)
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        cutoff = ref - timedelta(hours=1)
        baseline: Optional[dict[str, Any]] = None
        for snap in self.snapshots:
            snap_ts = _parse_iso(snap.get("ts"))
            if snap_ts is None:
                continue
            if snap_ts.tzinfo is None:
                snap_ts = snap_ts.replace(tzinfo=timezone.utc)
            if snap_ts <= cutoff:
                baseline = snap
        if baseline is None:
            return None
        return float(delta_between(baseline["count"], latest))

    def delta_since(
        self,
        since_iso_or_count_at_publish: Union[str, int, float],
    ) -> Optional[int]:
        """Delta from a publish-time count or ISO timestamp to latest.

        - If *since* is numeric: ``latest - count``.
        - If ISO string: find the last snapshot at or before that time
          (else earliest after) and return ``latest - that_count``.
        """
        latest = self.latest()
        if latest is None:
            return None
        if isinstance(since_iso_or_count_at_publish, (int, float)):
            return delta_between(since_iso_or_count_at_publish, latest)

        since = _parse_iso(str(since_iso_or_count_at_publish))
        if since is None:
            return None
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)

        best: Optional[dict[str, Any]] = None
        for snap in self.snapshots:
            snap_ts = _parse_iso(snap.get("ts"))
            if snap_ts is None:
                continue
            if snap_ts.tzinfo is None:
                snap_ts = snap_ts.replace(tzinfo=timezone.utc)
            if snap_ts <= since:
                best = snap
            elif best is None:
                best = snap
                break
            else:
                break
        if best is None:
            return None
        return delta_between(best["count"], latest)
