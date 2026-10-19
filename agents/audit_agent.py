#!/usr/bin/env python3
"""Deep repo audit agent (audit-project style) via OpenRouter — multi-lens review."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

# Priority source files for a release-style audit
TARGETS = [
    "bluesky_bot_v2.py",
    "content_service.py",
    "engagement_service.py",
    "state_service.py",
    "resilience_service.py",
    "openrouter_adapter.py",
    "verify_bot.py",
    "growth_engine.py",
]

LENSES = [
    {
        "id": "correctness",
        "title": "Correctness & reliability",
        "focus": "bugs, race conditions, error handling, state consistency, retry logic mistakes",
    },
    {
        "id": "security",
        "title": "Security",
        "focus": "secrets leakage, injection, unsafe deserialization, auth, SSRF, path traversal, log PII",
    },
    {
        "id": "ops",
        "title": "Ops & production readiness",
        "focus": "config, Docker/systemd, rate limits, resource leaks, observability, crash recovery",
    },
]


def load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def collect_sources(max_chars: int = 90000) -> str:
    chunks: list[str] = []
    used = 0
    for name in TARGETS:
        path = ROOT / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        block = f"\n\n===== FILE: {name} =====\n{text}"
        if used + len(block) > max_chars:
            remain = max_chars - used
            if remain > 500:
                chunks.append(block[:remain] + "\n...[truncated]...")
            break
        chunks.append(block)
        used += len(block)
    return "".join(chunks)


def call_openrouter(api_key: str, model: str, system: str, user: str) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        subprocess_install = [sys.executable, "-m", "pip", "install", "-q", "openai"]
        import subprocess

        subprocess.run(subprocess_install, check=False)
        from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    resp = client.chat.completions.create(
        model=model,
        temperature=0.1,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def review_lens(api_key: str, model: str, lens: dict, code: str) -> dict:
    system = (
        "You are a senior staff engineer performing a release audit of a Python Bluesky bot. "
        "Return ONLY valid JSON with shape: "
        '{"findings":[{"severity":"critical|high|medium|low","file":"str","issue":"str","why":"str","fix":"str"}]} '
        "Max 6 findings. Prefer concrete, actionable issues with file names from the provided code. "
        "If nothing serious, return {\"findings\":[]}."
    )
    user = (
        f"Lens: {lens['title']}\nFocus: {lens['focus']}\n"
        f"Project: BlueSky-bot (AI posting bot).\n"
        f"Code:\n{code}"
    )
    raw = call_openrouter(api_key, model, system, user)
    # Strip markdown fences if present
    cleaned = raw
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # try extract first {...}
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                parsed = {"findings": [], "parse_error": True, "raw": raw[:2000]}
        else:
            parsed = {"findings": [], "parse_error": True, "raw": raw[:2000]}
    return {"lens": lens["id"], "title": lens["title"], **parsed}


def main() -> int:
    load_dotenv()
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("[audit_agent] OPENROUTER_API_KEY missing", file=sys.stderr)
        return 2

    model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip() or "openai/gpt-4o-mini"
    REPORTS.mkdir(exist_ok=True)
    code = collect_sources()
    if not code.strip():
        print("[audit_agent] no source files found", file=sys.stderr)
        return 2

    results = []
    for lens in LENSES:
        print(f"[audit_agent] running lens: {lens['id']} ...")
        results.append(review_lens(api_key, model, lens, code))

    all_findings = []
    for r in results:
        for f in r.get("findings") or []:
            item = dict(f)
            item["lens"] = r.get("lens")
            all_findings.append(item)

    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    all_findings.sort(key=lambda x: severity_rank.get(str(x.get("severity", "low")).lower(), 9))

    report = {
        "agent": "audit_agent",
        "style": "audit-project multi-lens via OpenRouter",
        "model": model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "targets": [t for t in TARGETS if (ROOT / t).exists()],
        "summary": {
            "total_findings": len(all_findings),
            "by_severity": {
                s: sum(1 for f in all_findings if str(f.get("severity", "")).lower() == s)
                for s in ("critical", "high", "medium", "low")
            },
        },
        "lenses": results,
        "findings": all_findings,
    }

    out_json = REPORTS / "audit_agent_report.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "# Audit Agent Report",
        "",
        f"Model: `{model}`",
        f"Generated: `{report['generated_at']}`",
        f"Findings: **{report['summary']['total_findings']}** "
        f"(critical={report['summary']['by_severity']['critical']}, "
        f"high={report['summary']['by_severity']['high']}, "
        f"medium={report['summary']['by_severity']['medium']}, "
        f"low={report['summary']['by_severity']['low']})",
        "",
        "## Findings",
        "",
    ]
    if not all_findings:
        md_lines.append("_No findings._")
    for i, f in enumerate(all_findings, 1):
        md_lines += [
            f"### {i}. [{str(f.get('severity','?')).upper()}] {f.get('issue','')}",
            f"- Lens: `{f.get('lens')}`",
            f"- File: `{f.get('file','?')}`",
            f"- Why: {f.get('why','')}",
            f"- Fix: {f.get('fix','')}",
            "",
        ]
    (REPORTS / "audit_agent_report.md").write_text("\n".join(md_lines), encoding="utf-8")
    print(f"[audit_agent] report -> {out_json}")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
