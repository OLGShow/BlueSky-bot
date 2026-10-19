# `opt/` — deploy mirror + local runtime

This tree holds the **tracked deploy mirror** under `opt/bluesky-bot/` and
optional **local-only** runtime artifacts used when running the bot from
`/opt/bluesky-bot` (or a local checkout of that layout).

## Tracked mirror (committed)

Python modules under `opt/bluesky-bot/*.py` are a **flat copy** of the
application source of truth in [`app/`](../app/README.md). Keep them in sync
with:

```bash
bash packaging/sync-opt-from-sot.sh
```

Direction is one-way only: `app/` → `opt/bluesky-bot/`. Never copy modules
back into `app/`. See also [`packaging/sync-opt-from-sot.sh`](../packaging/sync-opt-from-sot.sh).

## Local-only (gitignored)

These paths may appear under `opt/bluesky-bot/` on a developer or server
machine; they are **not** part of the tracked mirror:

| Path / pattern | Purpose |
|----------------|---------|
| `venv/` | Local virtualenv |
| `bot.log*` | Runtime logs |
| memory / `bot_memory.*` | Local learning / memory state |

Do not commit secrets (`.env`), session files, or memory dumps.

### Optional: local log cleanup

If `bot.log*` grows large during local runs, truncate or delete those
log files locally. They are gitignored and safe to remove; do not treat
them as source of truth.

## Out of scope (this cycle)

**Do not** untrack `opt/*.py` (no Stage 5B). The tracked mirror remains
intentional until a later layout cycle decides otherwise.
