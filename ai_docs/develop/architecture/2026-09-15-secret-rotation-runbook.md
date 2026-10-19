# Secret Rotation & Git History Purge Runbook

**Date:** 2026-09-15  
**Audit IDs:** [S1]  
**Scope:** Operator-side credential rotation and **manual** git-history scrub after secrets were committed.  
**Audience:** Maintainers / server operators (not automated agents).

> **Never paste real secret values into git, issues, chat, or this document.**  
> Use placeholder names only: `BLUESKY_HANDLE`, `BLUESKY_PASSWORD`, `OPENAI_API_KEY`, and any other env keys you rotate.

---

## 1. Incident summary

Commit `8cfede2` on `origin/main` exposed environment variable **names and values** for at least:

| Variable (name only) | Purpose |
| --- | --- |
| `BLUESKY_PASSWORD` | Bluesky app password used by the bot |
| `BLUESKY_HANDLE` | Bluesky account handle |
| `OPENAI_API_KEY` | OpenAI API key used for content generation |

Treat those credentials as **compromised** until rotated and invalidated. Removing the file from the current tree is not enough — values remain reachable via git history until a history rewrite is performed (see §4).

Related risk: previously built Docker images that may have baked nested `.env` / session files into layers. After Docker hardening (SEC-003), rebuild images and assume any keys that may have been in old layers are also compromised until rotated.

---

## 2. Credential rotation checklist

Complete every item. Check boxes as you go.

### 2.1 Bluesky

- [ ] Sign in to the Bluesky account that matches `BLUESKY_HANDLE`.
- [ ] Revoke / delete the **app password** that was previously stored as `BLUESKY_PASSWORD`.
- [ ] Create a **new** app password (do not reuse the old one).
- [ ] Store the new value only in the server env file (see §3) — never in the repo.

### 2.2 OpenAI (and other API keys)

- [ ] In the OpenAI dashboard, **revoke / delete** the exposed `OPENAI_API_KEY`.
- [ ] Create a **new** API key.
- [ ] Rotate any other provider keys that may have shared the same `.env` (if present).
- [ ] Confirm old keys return auth errors when used.

### 2.3 Invalidate & verify

- [ ] Confirm old Bluesky app password no longer authenticates.
- [ ] Confirm old `OPENAI_API_KEY` is rejected by the API.
- [ ] Restart the bot service after updating env (see §3).
- [ ] Smoke-check: `systemctl status bluesky-bot` and recent `journalctl` for successful login / no auth failures.
- [ ] Ensure no `.env` (or copies) containing secrets is tracked by git: `git status`, `git check-ignore -v` on secret paths.

---

## 3. Update server config only (no secrets in git)

Canonical runtime location:

```text
/etc/bluesky-bot/.env
```

Steps:

1. Edit **only** the server file (example):

   ```bash
   sudo nano /etc/bluesky-bot/.env
   ```

2. Set placeholders — replace with real values **on the server only**:

   ```bash
   BLUESKY_HANDLE=your-bot.bsky.social
   BLUESKY_PASSWORD=your-new-app-password
   OPENAI_API_KEY=your-new-openai-key
   ```

3. Restrict permissions if needed (`chmod 600`, owner appropriate for the service user).

4. Restart:

   ```bash
   sudo systemctl restart bluesky-bot
   ```

5. **Do not** commit `/etc/bluesky-bot/.env`, local `.env`, export trees under `etc/` / `opt/`, or any file containing live secrets.

6. Prefer a single secrets location outside the repo; scrub local export copies so they do not reintroduce values into the working tree.

---

## 4. Git history purge — MANUAL USER STEPS ONLY

> **Operators only.** Do **not** ask an automated agent / CI / orchestrator to run `git push --force`, `git filter-repo`, or BFG against production remotes.  
> History rewrite requires explicit human coordination and a force-push that rewrites shared history.

### 4.1 Before you start

- [ ] All credentials from §2 are rotated and invalidated (rewrite does **not** undo past leakage to clones/mirrors).
- [ ] Notify all collaborators: stop pushing; sync after the rewrite.
- [ ] Decide who performs the rewrite and who force-pushes (one owner).
- [ ] Back up the current remote tip (clone or note the pre-rewrite SHA).
- [ ] Confirm branch protection / who can force-push to `main`.

### 4.2 Option A — `git filter-repo` (recommended)

On a **fresh clone**, as the human operator:

```bash
# Install git-filter-repo if needed, then from a clean clone:
git filter-repo --path .env --invert-paths
# Or purge by blob / pathspecs that contained secrets (adjust to your tree):
# git filter-repo --path-glob '**/.env' --invert-paths
```

Review rewritten history locally. Then, **only the operator** coordinates a force-push with the team:

```bash
# HUMAN ONLY — after team agreement. Do not automate.
git push --force-with-lease origin main
```

Collaborators must re-clone or hard-reset to the new history (document the agreed procedure for your team).

### 4.3 Option B — BFG Repo-Cleaner

On a **fresh mirror clone**, as the human operator:

```bash
git clone --mirror <remote-url> bluesky-bot.mirror
# Run BFG to delete files that held secrets, e.g.:
# bfg --delete-files .env bluesky-bot.mirror
cd bluesky-bot.mirror
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

Then force-push the mirror **only as a manual operator step** after coordination:

```bash
# HUMAN ONLY — after team agreement. Do not automate.
git push --force
```

### 4.4 After rewrite

- [ ] Verify `.env` / secret blobs are gone from history (`git log --all --full-history -- .env` should be empty or expected).
- [ ] Re-enable / tighten branch protection on `main` (disallow casual force-push).
- [ ] Ask collaborators to discard old clones that still contain the leaked blobs.
- [ ] Rebuild any Docker images from clean context; discard old tags/layers that may have contained secrets.
- [ ] Confirm server still uses **new** keys from `/etc/bluesky-bot/.env` only.

---

## 5. What this runbook does *not* do

- Does not rotate keys for you.
- Does not rewrite remote history automatically.
- Does not authorize agents to force-push.
- Does not store or reproduce any real secret values.

---

## References

- Audit finding [S1]: `ai_docs/develop/audits/2026-09-15-full-project-audit.md`
- Remediation plan SEC-002: `ai_docs/develop/plans/2026-09-15-critical-audit-remediation.md`
- Server env path: `/etc/bluesky-bot/.env`
