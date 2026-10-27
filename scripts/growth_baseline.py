#!/usr/bin/env python3
"""W0 baseline dump helper — run on host cwd `/opt/bluesky-bot` or with --path.

Writes JSON to stdout; optionally ``--out reports/growth_baseline_YYYY-MM-DD.json``.
Does not change bot runtime behavior.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


def collect(cwd: Path) -> dict:
    out: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cwd": str(cwd),
        "window_days": 7,
    }
    ff = json.loads((cwd / "learning_followers.json").read_text(encoding="utf-8"))
    sn = ff.get("snapshots") or []
    by_day: dict = {}
    for s in sn:
        day = str(s.get("ts", ""))[:10]
        by_day[day] = s.get("count")
    out["followers_by_day"] = dict(sorted(by_day.items()))
    if sn:
        out["followers_first"] = sn[0]
        out["followers_last"] = sn[-1]
        out["followers_delta_all"] = int(sn[-1]["count"]) - int(sn[0]["count"])
    days = sorted(by_day)
    if len(days) >= 2:
        cut = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
        last7 = [d for d in days if d >= cut]
        if len(last7) >= 2:
            out["followers_delta_7d"] = by_day[last7[-1]] - by_day[last7[0]]
            out["followers_7d_span"] = [
                last7[0],
                last7[-1],
                by_day[last7[0]],
                by_day[last7[-1]],
            ]

    log_path = cwd / "bot.log"
    text = log_path.read_text(errors="replace") if log_path.exists() else ""
    posts = likes = follows = errors = sessions = 0
    for ln in text.splitlines():
        m = re.search(r"Статистика сессии: (\{.*\})", ln)
        if not m:
            continue
        try:
            d = eval(m.group(1))  # trusted local bot.log
        except Exception:
            continue
        sessions += 1
        posts += d.get("posts_created", 0)
        likes += d.get("likes_given", 0)
        follows += d.get("follows_made", 0)
        errors += d.get("errors", 0)
    out["session_stats_parsed"] = {
        "sessions": sessions,
        "posts": posts,
        "likes": likes,
        "follows": follows,
        "errors": errors,
        "like_per_follow": round(likes / max(follows, 1), 2),
    }
    out["podpisor_sdelano_sum"] = sum(
        int(x) for x in re.findall(r"Подписок сделано: (\d+)", text)
    )
    out["follow_pass_done_lines"] = len(re.findall(r"Follow pass done:", text))
    out["traceback_count"] = text.count("Traceback")
    out["error_log_lines"] = len(re.findall(r" - ERROR - ", text))
    out["http_429_approx"] = len(re.findall(r"\b429\b", text))

    dec_path = cwd / "reports" / "agent_decisions.jsonl"
    if dec_path.exists():
        days_c: Counter = Counter()
        dom: Counter = Counter()
        act: Counter = Counter()
        cut = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        n = n7 = 0
        for ln in dec_path.read_text(encoding="utf-8").splitlines():
            try:
                o = json.loads(ln)
            except Exception:
                continue
            n += 1
            ts = str(o.get("ts") or "")
            if ts >= cut:
                n7 += 1
                days_c[ts[:10]] += 1
                dom[o.get("domain") or "?"] += 1
                act[o.get("action") or "?"] += 1
        out["agent_decisions_total"] = n
        out["agent_decisions_7d"] = n7
        out["decisions_by_day_7d"] = dict(sorted(days_c.items()))
        out["domains_7d"] = dict(dom)
        out["actions_7d"] = dict(act)

    cfg_path = cwd / "bot_config.json"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        out["follow_strategy"] = cfg.get("follow_strategy")
        out["llm_retro_dry_run"] = (cfg.get("llm_retro") or {}).get("dry_run")
        out["engagement_mode"] = cfg.get("engagement_mode")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--path", type=Path, default=Path("."))
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    data = collect(args.path.resolve())
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}", flush=True)
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
