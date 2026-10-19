#!/usr/bin/env python3
"""Local PR-style review agent (pr-agent analogue) — reviews git diff via OpenRouter."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


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


def git_diff(max_chars: int = 60000) -> tuple[str, str]:
    """Return (base_ref, diff_text). Prefer unstaged+staged vs HEAD, else last commit."""
    for cmd in (
        ["git", "diff", "HEAD"],
        ["git", "diff", "--cached"],
    ):
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.stdout.strip():
            return " ".join(cmd), p.stdout[:max_chars]

    p = subprocess.run(
        ["git", "diff", "HEAD~1...HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if p.stdout.strip():
        return "HEAD~1...HEAD", p.stdout[:max_chars]

    # Fallback: list recent tracked py files as pseudo-diff context
    files = []
    for name in (
        "bluesky_bot_v2.py",
        "content_service.py",
        "engagement_service.py",
        "state_service.py",
        "openrouter_adapter.py",
    ):
        path = ROOT / name
        if path.exists():
            files.append(f"===== {name} =====\n" + path.read_text(encoding="utf-8", errors="replace")[:8000])
    return "full-file-fallback", "\n\n".join(files)[:max_chars]


def call_openrouter(api_key: str, model: str, diff: str, base: str) -> dict:
    try:
        from openai import OpenAI
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openai"], check=False)
        from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    system = (
        "You are PR-Agent style reviewer. Return ONLY JSON: "
        "{"
        '"score":0-100,'
        '"summary":"str",'
        '"security":["str"],'
        '"issues":[{"severity":"critical|high|medium|low","file":"str","issue":"str","suggestion":"str"}],'
        '"improvements":[{"file":"str","suggestion":"str"}]'
        "}. Max 8 issues, max 5 improvements. Be concrete."
    )
    user = f"Review base=`{base}` for BlueSky-bot.\n\nDIFF/CODE:\n{diff}"
    resp = client.chat.completions.create(
        model=model,
        temperature=0.1,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    raw = (resp.choices[0].message.content or "").strip()
    cleaned = raw
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass
        return {"score": 0, "summary": "parse_error", "raw": raw[:3000], "issues": [], "improvements": [], "security": []}


def main() -> int:
    load_dotenv()
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("[pr_review_agent] OPENROUTER_API_KEY missing", file=sys.stderr)
        return 2
    model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip() or "openai/gpt-4o-mini"

    REPORTS.mkdir(exist_ok=True)
    base, diff = git_diff()
    print(f"[pr_review_agent] reviewing: {base} ({len(diff)} chars)")
    review = call_openrouter(api_key, model, diff, base)

    report = {
        "agent": "pr_review_agent",
        "style": "pr-agent local analogue via OpenRouter",
        "model": model,
        "base": base,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "review": review,
    }
    out = REPORTS / "pr_review_agent_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    issues = review.get("issues") or []
    md = [
        "# PR Review Agent Report",
        "",
        f"Score: **{review.get('score', '?')}/100**",
        f"Base: `{base}`",
        f"Model: `{model}`",
        "",
        "## Summary",
        str(review.get("summary", "")),
        "",
        "## Security notes",
    ]
    for s in review.get("security") or ["_none_"]:
        md.append(f"- {s}")
    md += ["", "## Issues", ""]
    if not issues:
        md.append("_No issues._")
    for i, issue in enumerate(issues, 1):
        md.append(
            f"{i}. **[{str(issue.get('severity','?')).upper()}]** `{issue.get('file','?')}` — "
            f"{issue.get('issue','')}\n   - Suggestion: {issue.get('suggestion','')}"
        )
    md += ["", "## Improvements", ""]
    for imp in review.get("improvements") or []:
        md.append(f"- `{imp.get('file','?')}`: {imp.get('suggestion','')}")

    (REPORTS / "pr_review_agent_report.md").write_text("\n".join(md), encoding="utf-8")
    print(f"[pr_review_agent] report -> {out}")
    print(json.dumps({"score": review.get("score"), "issues": len(issues)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
