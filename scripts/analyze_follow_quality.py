#!/usr/bin/env python3
"""W1-008 — offline join of outbound follow decisions × follower cohort.

Reads ``reports/agent_decisions.jsonl`` (domain=follow) and optionally
``learning_followers_cohort.json`` / ``reports/followers_daily_*.json``.

Writes ``reports/follow_quality_YYYY-MM-DD.json`` with reason/source counts
and a retention section (placeholders until ≥7d cohort history exists;
optional rough proxy when ever_seen / churned_history are available).

Hermetic: missing/empty inputs produce a valid report (no network).
Does not modify bot config or dry_run.

Usage:
  python scripts/analyze_follow_quality.py
  python scripts/analyze_follow_quality.py \\
    --decisions reports/agent_decisions.jsonl \\
    --cohort-state learning_followers_cohort.json \\
    --out reports/follow_quality_2026-10-27.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

KNOWN_REASONS = ("quality_ok", "keyword", "liked_enough")
KNOWN_SOURCES = ("suggestions", "timeline")
MIN_HISTORY_DAYS_FOR_FULL_JOIN = 7

RETENTION_NOTE = (
    "Full retention join (48h / 7d) needs ≥7d of cohort snapshot history; "
    "when history is thinner, retention fields are placeholders or a rough "
    "ever_seen/churned proxy only."
)


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_json(path: Path) -> Optional[Any]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_follow_decisions(path: Path) -> list[dict[str, Any]]:
    """Parse JSONL; keep domain=follow rows. Missing file → []."""
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if str(row.get("domain") or "") != "follow":
            continue
        out.append(row)
    return out


def _context_did(row: Mapping[str, Any]) -> str:
    ctx = row.get("context")
    if not isinstance(ctx, Mapping):
        return ""
    return str(ctx.get("did") or "").strip()


def count_by_reason(events: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in events:
        reason = str(row.get("reason") or "").strip() or "unknown"
        if reason not in KNOWN_REASONS:
            reason = "other" if reason else "unknown"
        counts[reason] += 1
    # Stable keys for known reasons even when zero.
    result = {k: int(counts.get(k, 0)) for k in KNOWN_REASONS}
    for key, n in counts.items():
        if key not in result:
            result[key] = int(n)
    return result


def count_by_source(events: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Source is logged as ``arm`` (suggestions / timeline)."""
    counts: Counter[str] = Counter()
    for row in events:
        source = str(row.get("arm") or "").strip() or "unknown"
        if source not in KNOWN_SOURCES:
            source = "other" if source else "unknown"
        counts[source] += 1
    result = {k: int(counts.get(k, 0)) for k in KNOWN_SOURCES}
    for key, n in counts.items():
        if key not in result:
            result[key] = int(n)
    return result


def _cohort_history_span_days(history: list[Any]) -> float:
    stamps: list[datetime] = []
    for item in history:
        if not isinstance(item, Mapping):
            continue
        dt = _parse_ts(item.get("ts"))
        if dt is not None:
            stamps.append(dt)
    if len(stamps) < 2:
        return 0.0
    stamps.sort()
    return max(0.0, (stamps[-1] - stamps[0]).total_seconds() / 86400.0)


def _normalize_follow_id(
    did: str,
    *,
    mode: str,
    hash_hex_len: int,
) -> str:
    if not did:
        return ""
    try:
        from follower_analytics import normalize_id

        return normalize_id(did, mode, hash_hex_len=hash_hex_len)
    except Exception:
        return did


def load_cohort_bundle(
    state_path: Path,
    *,
    reports_dir: Path,
) -> dict[str, Any]:
    """Load cohort state + optional daily report files (best-effort)."""
    raw = _load_json(state_path)
    try:
        from follower_analytics import normalize_state

        state = normalize_state(raw if isinstance(raw, Mapping) else None)
    except Exception:
        state = {
            "mode": "full",
            "hash_hex_len": 16,
            "prev": [],
            "ever_seen": [],
            "churned_history": [],
            "history": [],
            "updated_at": None,
        }
        if isinstance(raw, Mapping):
            for key in (
                "mode",
                "hash_hex_len",
                "prev",
                "ever_seen",
                "churned_history",
                "history",
                "updated_at",
            ):
                if key in raw:
                    state[key] = raw[key]

    daily: list[dict[str, Any]] = []
    if reports_dir.is_dir():
        for path in sorted(reports_dir.glob("followers_daily_*.json")):
            payload = _load_json(path)
            if isinstance(payload, dict):
                daily.append({"path": str(path), **payload})

    history = state.get("history") if isinstance(state.get("history"), list) else []
    prev = set(state.get("prev") or [])
    ever_seen = set(state.get("ever_seen") or [])
    churned = set(state.get("churned_history") or [])
    loaded = state_path.is_file() and isinstance(raw, Mapping)

    return {
        "loaded": loaded,
        "state_path": str(state_path),
        "mode": str(state.get("mode") or "full"),
        "hash_hex_len": int(state.get("hash_hex_len") or 16),
        "updated_at": state.get("updated_at"),
        "prev": prev,
        "ever_seen": ever_seen,
        "churned_history": churned,
        "history": history,
        "history_len": len(history),
        "history_span_days": _cohort_history_span_days(history),
        "daily_reports": daily,
        "daily_reports_found": len(daily),
        "prev_size": len(prev),
        "ever_seen_size": len(ever_seen),
        "churned_history_size": len(churned),
    }


def retention_proxy(
    events: list[Mapping[str, Any]],
    cohort: Mapping[str, Any],
) -> dict[str, Any]:
    """Rough membership proxy: DID in prev vs churned_history vs unknown.

    Not a true 48h/7d survival curve — only usable when cohort sets exist.
    """
    prev = set(cohort.get("prev") or [])
    ever_seen = set(cohort.get("ever_seen") or [])
    churned = set(cohort.get("churned_history") or [])
    mode = str(cohort.get("mode") or "full")
    hex_len = int(cohort.get("hash_hex_len") or 16)

    proxy_available = bool(ever_seen or prev or churned)
    still = churned_n = unknown = matched = 0
    by_reason_still: Counter[str] = Counter()
    by_reason_churned: Counter[str] = Counter()
    by_reason_matched: Counter[str] = Counter()

    for row in events:
        did = _context_did(row)
        if not did:
            continue
        nid = _normalize_follow_id(did, mode=mode, hash_hex_len=hex_len)
        if not nid:
            continue
        if nid not in ever_seen and nid not in prev and nid not in churned:
            # Never observed in cohort — skip (outbound follow ≠ follower).
            continue
        matched += 1
        reason = str(row.get("reason") or "unknown")
        by_reason_matched[reason] += 1
        if nid in prev:
            still += 1
            by_reason_still[reason] += 1
        elif nid in churned:
            churned_n += 1
            by_reason_churned[reason] += 1
        else:
            # In ever_seen but neither current nor churned pool.
            unknown += 1

    rate = round(still / matched, 4) if matched else None
    span = float(cohort.get("history_span_days") or 0.0)
    hist_len = int(cohort.get("history_len") or 0)
    sufficient = span >= MIN_HISTORY_DAYS_FOR_FULL_JOIN or hist_len >= (
        MIN_HISTORY_DAYS_FOR_FULL_JOIN + 1
    )

    return {
        "sufficient_history_for_full_join": sufficient,
        "cohort_history_len": hist_len,
        "cohort_history_span_days": round(span, 2),
        "min_days_required": MIN_HISTORY_DAYS_FOR_FULL_JOIN,
        "proxy_available": proxy_available,
        "matched_in_cohort": matched,
        "still_following_proxy": still,
        "churned_proxy": churned_n,
        "unknown_membership_proxy": unknown,
        "retention_rate_proxy": rate,
        "by_reason_matched": dict(by_reason_matched),
        "by_reason_still_following_proxy": dict(by_reason_still),
        "by_reason_churned_proxy": dict(by_reason_churned),
        "retention_48h": None,
        "retention_7d": None,
        "note_48h": (
            "Placeholder until cohort snapshots cover ≥48h after follow events."
        ),
        "note_7d": (
            "Placeholder until cohort snapshots cover ≥7d after follow events."
        ),
    }


def build_report(
    *,
    decisions_path: Path,
    cohort_state_path: Path,
    reports_dir: Path,
    out_date: str,
) -> dict[str, Any]:
    events = load_follow_decisions(decisions_path)
    cohort = load_cohort_bundle(cohort_state_path, reports_dir=reports_dir)
    retention = retention_proxy(events, cohort)

    return {
        "generated_at": _utc_now_iso(),
        "date": out_date,
        "decisions_path": str(decisions_path),
        "cohort_state_path": str(cohort_state_path),
        "reports_dir": str(reports_dir),
        "follow_events_total": len(events),
        "counts_by_reason": count_by_reason(events),
        "counts_by_source": count_by_source(events),
        "retention_note": RETENTION_NOTE,
        "retention": retention,
        "cohort": {
            "loaded": bool(cohort.get("loaded")),
            "updated_at": cohort.get("updated_at"),
            "mode": cohort.get("mode"),
            "prev_size": int(cohort.get("prev_size") or 0),
            "ever_seen_size": int(cohort.get("ever_seen_size") or 0),
            "churned_history_size": int(cohort.get("churned_history_size") or 0),
            "history_len": int(cohort.get("history_len") or 0),
            "history_span_days": cohort.get("history_span_days"),
            "daily_reports_found": int(cohort.get("daily_reports_found") or 0),
        },
    }


def default_out_path(reports_dir: Path, day: Optional[str] = None) -> Path:
    return reports_dir / f"follow_quality_{day or _utc_today()}.json"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Join follow decisions with cohort for quality/retention report."
    )
    ap.add_argument(
        "--decisions",
        type=Path,
        default=Path("reports") / "agent_decisions.jsonl",
        help="Path to agent_decisions.jsonl (default: reports/agent_decisions.jsonl)",
    )
    ap.add_argument(
        "--cohort-state",
        type=Path,
        default=Path("learning_followers_cohort.json"),
        help="Path to learning_followers_cohort.json",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path (default: reports/follow_quality_YYYY-MM-DD.json)",
    )
    ap.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("reports"),
        help="Directory for followers_daily_*.json discovery (default: reports)",
    )
    args = ap.parse_args(argv)

    reports_dir = args.reports_dir
    out_path = args.out or default_out_path(reports_dir)
    # Prefer date from --out stem when present.
    out_date = _utc_today()
    stem = out_path.stem
    if stem.startswith("follow_quality_") and len(stem) >= len("follow_quality_YYYY-MM-DD"):
        maybe = stem.replace("follow_quality_", "", 1)
        if len(maybe) == 10 and maybe[4] == "-" and maybe[7] == "-":
            out_date = maybe

    report = build_report(
        decisions_path=args.decisions,
        cohort_state_path=args.cohort_state,
        reports_dir=reports_dir,
        out_date=out_date,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(payload, encoding="utf-8")
    print(f"wrote {out_path}", flush=True)
    print(
        f"follow_events={report['follow_events_total']} "
        f"reasons={report['counts_by_reason']} "
        f"sources={report['counts_by_source']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
