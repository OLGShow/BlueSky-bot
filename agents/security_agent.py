#!/usr/bin/env python3
"""Security gate agent (RepoRook-style): bandit + pip-audit + secret heuristics."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
PIP_AUDIT_TIMEOUT_S = 120
SECRET_PATTERNS = [
    (re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*=\s*['\"][^'\"]{8,}['\"]"), "hardcoded_secret_assignment"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "openai_like_key"),
    (re.compile(r"sk-or-v1-[a-zA-Z0-9]{20,}"), "openrouter_key"),
    (re.compile(r"(?i)Bearer\s+[A-Za-z0-9\-._~+/]+=*"), "bearer_token"),
]
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", "reports", "var"}


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Hard-kill proc and children so a hung network tool cannot outlive the timeout."""
    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=15,
                check=False,
            )
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                proc.kill()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def _run(cmd: list[str], timeout: int = 180) -> tuple[int, str, str]:
    """Run a command with a hard wall-clock timeout; kill the process tree on expiry."""
    popen_kwargs: dict = {
        "cwd": ROOT,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if sys.platform == "win32":
        # New process group so taskkill /T can reap pip-audit children.
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
    except FileNotFoundError as e:
        return 127, "", str(e)

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return proc.returncode if proc.returncode is not None else 0, stdout or "", stderr or ""
    except subprocess.TimeoutExpired:
        _kill_process_tree(proc)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
        out = stdout if isinstance(stdout, str) else ""
        err = stderr if isinstance(stderr, str) and stderr else f"timeout after {timeout}s"
        return 124, out, err


def ensure_tools() -> list[str]:
    notes: list[str] = []
    for pkg in ("bandit", "pip-audit"):
        code, _, err = _run([sys.executable, "-m", "pip", "show", pkg])
        if code != 0:
            notes.append(f"installing {pkg}")
            _run([sys.executable, "-m", "pip", "install", "-q", pkg])
    return notes


def scan_secrets() -> list[dict]:
    findings: list[dict] = []
    for path in ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if "os.getenv" in line or "environ" in line or line.strip().startswith("#"):
                continue
            for pattern, kind in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        {
                            "severity": "high",
                            "kind": kind,
                            "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                            "line": i,
                            "snippet": line.strip()[:120],
                        }
                    )
    return findings


def run_bandit() -> dict:
    out_json = REPORTS / "security_bandit.json"
    code, stdout, stderr = _run(
        [
            sys.executable,
            "-m",
            "bandit",
            "-r",
            ".",
            "-f",
            "json",
            "-o",
            str(out_json),
            "-x",
            ".venv,venv,tests,.git,reports,var,__pycache__",
            "-q",
        ]
    )
    data: dict = {"returncode": code, "issues": []}
    if out_json.exists():
        try:
            raw = json.loads(out_json.read_text(encoding="utf-8"))
            data["issues"] = [
                {
                    "severity": i.get("issue_severity", "UNKNOWN"),
                    "test_id": i.get("test_id"),
                    "text": i.get("issue_text"),
                    "file": i.get("filename"),
                    "line": i.get("line_number"),
                }
                for i in raw.get("results", [])
            ]
            data["metrics"] = raw.get("metrics", {})
        except json.JSONDecodeError:
            data["parse_error"] = True
            data["stdout"] = stdout[-2000:]
            data["stderr"] = stderr[-2000:]
    else:
        data["stderr"] = stderr[-2000:]
        data["stdout"] = stdout[-2000:]
    return data


def run_pip_audit() -> dict:
    req = ROOT / "requirements.txt"
    if not req.exists():
        return {"skipped": True, "reason": "no requirements.txt"}
    # Network advisory lookup can hang; hard wall-clock timeout + process-tree kill.
    code, stdout, stderr = _run(
        [sys.executable, "-m", "pip_audit", "-r", str(req), "--format", "json", "--progress-spinner", "off"],
        timeout=PIP_AUDIT_TIMEOUT_S,
    )
    if code == 124:
        return {
            "returncode": 124,
            "timeout": True,
            "timeout_seconds": PIP_AUDIT_TIMEOUT_S,
            "vulnerabilities": [],
            "stderr": stderr,
            "non_blocking": True,
        }
    vulns: list = []
    if stdout.strip():
        try:
            parsed = json.loads(stdout)
            # pip-audit json: list of {name, version, vulns:[...]} or newer schema
            if isinstance(parsed, list):
                for pkg in parsed:
                    for v in pkg.get("vulns", []) or []:
                        vulns.append(
                            {
                                "package": pkg.get("name"),
                                "version": pkg.get("version"),
                                "id": v.get("id"),
                                "fix_versions": v.get("fix_versions"),
                                "description": (v.get("description") or "")[:200],
                            }
                        )
            elif isinstance(parsed, dict) and "dependencies" in parsed:
                for pkg in parsed.get("dependencies", []):
                    for v in pkg.get("vulns", []) or []:
                        vulns.append(
                            {
                                "package": pkg.get("name"),
                                "version": pkg.get("version"),
                                "id": v.get("id"),
                                "fix_versions": v.get("fix_versions"),
                                "description": (v.get("description") or "")[:200],
                            }
                        )
        except json.JSONDecodeError:
            return {"returncode": code, "parse_error": True, "stdout": stdout[-3000:], "stderr": stderr[-2000:]}
    return {"returncode": code, "vulnerabilities": vulns, "stderr": stderr[-1000:] if stderr else ""}


def main() -> int:
    REPORTS.mkdir(exist_ok=True)
    install_notes = ensure_tools()
    secrets = scan_secrets()
    bandit = run_bandit()
    pip_audit = run_pip_audit()

    high_bandit = [i for i in bandit.get("issues", []) if str(i.get("severity", "")).upper() in {"HIGH", "CRITICAL"}]
    report = {
        "agent": "security_agent",
        "style": "RepoRook-lite (bandit + pip-audit + secret heuristics)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "install_notes": install_notes,
        "summary": {
            "secret_findings": len(secrets),
            "bandit_issues": len(bandit.get("issues", [])),
            "bandit_high": len(high_bandit),
            "pip_audit_vulns": len(pip_audit.get("vulnerabilities", [])),
        },
        "secrets": secrets,
        "bandit": bandit,
        "pip_audit": pip_audit,
    }

    out = REPORTS / "security_agent_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md = REPORTS / "security_agent_report.md"
    lines = [
        "# Security Agent Report",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "## Summary",
        f"- Secrets: **{report['summary']['secret_findings']}**",
        f"- Bandit issues: **{report['summary']['bandit_issues']}** (high: {report['summary']['bandit_high']})",
        f"- pip-audit vulns: **{report['summary']['pip_audit_vulns']}**",
        "",
    ]
    if secrets:
        lines += ["## Secrets", ""]
        for s in secrets[:30]:
            lines.append(f"- `{s['file']}:{s['line']}` — {s['kind']}: `{s['snippet']}`")
        lines.append("")
    if high_bandit:
        lines += ["## Bandit HIGH+", ""]
        for i in high_bandit[:30]:
            lines.append(f"- `{i.get('file')}:{i.get('line')}` [{i.get('test_id')}] {i.get('text')}")
        lines.append("")
    if pip_audit.get("timeout"):
        lines += [
            "## pip-audit",
            "",
            f"- Timed out after **{pip_audit.get('timeout_seconds', PIP_AUDIT_TIMEOUT_S)}s** (non-blocking; no vulns recorded).",
            "",
        ]
    if pip_audit.get("vulnerabilities"):
        lines += ["## Dependency vulnerabilities", ""]
        for v in pip_audit["vulnerabilities"][:30]:
            lines.append(f"- `{v.get('package')}@{v.get('version')}` — {v.get('id')}")
        lines.append("")
    md.write_text("\n".join(lines), encoding="utf-8")

    print(f"[security_agent] report -> {out}")
    print(json.dumps(report["summary"], ensure_ascii=False))
    # Non-zero if high-risk findings; pip-audit timeout is non-blocking (empty vulns).
    if secrets or high_bandit or pip_audit.get("vulnerabilities"):
        return 1
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
