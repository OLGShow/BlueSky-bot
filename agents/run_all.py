#!/usr/bin/env python3
"""Run all local review agents and write a combined summary."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"

AGENTS_TO_RUN = (
    ("security_agent", AGENTS / "security_agent.py"),
    ("pr_review_agent", AGENTS / "pr_review_agent.py"),
    ("audit_agent", AGENTS / "audit_agent.py"),
)


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    results = []
    for name, script in AGENTS_TO_RUN:
        print(f"\n======== RUNNING {name} ========")
        p = subprocess.run(
            [sys.executable, "-u", str(script)],
            cwd=ROOT,
            env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONUNBUFFERED": "1"},
        )
        results.append({"agent": name, "exit_code": p.returncode})

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "reports": {
            "security": "reports/security_agent_report.md",
            "pr_review": "reports/pr_review_agent_report.md",
            "audit": "reports/audit_agent_report.md",
        },
    }
    out = REPORTS / "agents_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n======== DONE ========")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    # Prefer success of LLM agents; security may exit 1 on findings
    llm_ok = all(r["exit_code"] in (0, 1) for r in results)
    return 0 if llm_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
