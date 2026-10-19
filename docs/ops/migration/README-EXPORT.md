# Local export target (MIG-006 → MIG-009 ✅)

**Path:** `G:\cursor\BlueSky-bot`  
**Orchestration:** `orch-2026-09-15-14-10-paris-warsaw-mig`  
**Prepared:** 2026-09-15 · **Restored:** 2026-09-15 (MIG-007) · **Paris cleaned:** 2026-09-15 (MIG-008)

## Source / scope

| Item | Value |
|------|--------|
| Source | Paris (`hiplet-23630`, `138.124.31.250`) |
| Project | `bluesky-bot` only |
| VPN | **Excluded** — Amnezia on Paris stays on Paris; not part of this export |
| Warsaw | **Not configured** — deploy/cutover cancelled/deferred (Path B → LOCAL) |

## Structure

Server-layout staging dirs matching MIG-005 archive roots (existing local project left intact):

```
etc/bluesky-bot/          # includes .env (secret — gitignored)
etc/systemd/system/
etc/apt/sources.list.d/
opt/bluesky-bot/          # code + Linux venv + logs
var/lib/bluesky-bot/      # runtime state
systemd/bluesky-bot.service
EXPORT-MANIFEST.md
```

## MIG-007 status

- ✅ Backup SHA-256 verified
- ✅ Extracted into `etc/` / `opt/` / `var/`
- ✅ Rotated logs + current `bot.log` supplemented from live Paris
- ✅ Critical paths present — see **EXPORT-MANIFEST.md**

## Next

- ✅ **Completed** — MIG-008 cleanup done (bluesky-bot removed from Paris); MIG-009 docs done
- Local export kept; do **not** delete this folder as the restore source
- VPN on Paris: untouched / healthy (do not change)
