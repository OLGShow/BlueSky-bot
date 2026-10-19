# EXPORT-MANIFEST — MIG-007 (orch complete through MIG-009)

**Status:** ✅ Restored + Paris cleanup done  
**Orchestration:** `orch-2026-09-15-14-10-paris-warsaw-mig`  
**Restored (UTC):** 2026-09-15T12:10:00Z  
**Destination:** `G:\cursor\BlueSky-bot`  
**Layout:** root staging dirs from README-EXPORT (`etc/`, `opt/`, `var/`) — pre-existing local git project files left intact

## Source backup

| Field | Value |
|-------|-------|
| Archive | `G:\cursor\париж+варшава\backups\mig-005-bluesky-bot-20260915T115436Z.tar.gz` |
| Size | 32 687 045 bytes |
| SHA-256 | `f2a29f94899efda88aa1646dfe7784e9829639286a6fe031d61a62621034b015` |
| Checksum verify | ✅ match |
| Archive members | 7456 paths (697 dirs / 6748 files / 11 other) |

## Layout used

```
G:\cursor\BlueSky-bot\
├── etc\bluesky-bot\          # config + .env (secrets — do not commit)
├── etc\systemd\system\       # bluesky-bot.service
├── etc\apt\sources.list.d\   # bluesky-bot.list
├── opt\bluesky-bot\          # app code, Linux venv, logs, reports
├── var\lib\bluesky-bot\      # runtime state
├── systemd\bluesky-bot.service   # convenience copy (MIG-006 staging)
├── EXPORT-MANIFEST.md
├── README-EXPORT.md
└── … existing local project (untouched) …
```

`from-paris/` **not** used — README-EXPORT already defined `etc/` / `opt/` / `var/` at repo root.

## Staging tree sizes (after restore + Paris supplement)

| Tree | Files | Dirs | Bytes | MiB |
|------|------:|-----:|------:|----:|
| `etc/` | 4 | 5 | 8 796 | ~0.0 |
| `opt/` | 6 751 | 696 | 234 170 605 | ~223.3 |
| `var/` | 7 | 2 | 25 153 402 | ~24.0 |
| **Total staging** | **6 762** | **703** | **259 332 803** | **~247.3** |

## Critical files checklist

| Path | Present | Size (bytes) | Notes |
|------|:------:|-------------:|-------|
| `etc/bluesky-bot/.env` | ✅ | 1 498 | From MIG-005 archive; live mtime Apr 2026 (unchanged) |
| `etc/bluesky-bot/bot_config.json` | ✅ | 6 432 | Archive + live SCP refresh |
| `etc/systemd/system/bluesky-bot.service` | ✅ | 794 | Archive + live SCP |
| `etc/apt/sources.list.d/bluesky-bot.list` | ✅ | 72 | From archive |
| `opt/bluesky-bot/bluesky_bot_v2.py` | ✅ | 208 672 | From archive |
| `opt/bluesky-bot/venv/` | ✅ | (tree) | Linux x86_64 venv from archive |
| `opt/bluesky-bot/bot.log` | ✅ | 3 709 081 | Live SCP (newer than backup) |
| `opt/bluesky-bot/bot.log.[1-5]` | ✅ | ~20 MiB each | Live SCP (excluded from MIG-005) |
| `var/lib/bluesky-bot/bot_memory.json` | ✅ | 2 680 805 | From archive (see note) |
| `var/lib/bluesky-bot/session.json` | ✅ | 891 | From archive |
| `var/lib/bluesky-bot/action_ledger.jsonl` | ✅ | 175 412 | From archive (see note) |
| `var/lib/bluesky-bot/audit.log` | ✅ | 1 324 845 | Live SCP |
| `var/lib/bluesky-bot/bot_heartbeat.txt` | ✅ | 54 | Live SCP |
| `var/lib/bluesky-bot/bot.log` | ✅ | 20 971 395 | Live SCP (stale rotation target of bot.log.6) |
| `systemd/bluesky-bot.service` | ✅ | 794 | Mirror of unit |

## Live Paris supplement (at MIG-007 restore time)

| Item | Result |
|------|--------|
| Host | `paris` (`hiplet-23630`) — bot was active during export; **removed in MIG-008** |
| Readable via SCP | `bot_config.json`, unit, `audit.log`, heartbeat, `bot.log`, `bot.log.1–5`, var stale `bot.log` |
| Mode `600` (needs sudo) | live `.env`, `bot_memory.json`, `session.json`, `action_ledger.jsonl` — **not refreshed**; kept from verified MIG-005 archive |
| Live delta (observed, not copied) | `bot_memory.json` 2 681 016 vs archive 2 680 805 (~211 B); ledger 175 499 vs 175 412 (~87 B) |
| VPN / Amnezia | **not touched** (still healthy on Paris after cleanup) |

## Symlink handling (Windows)

Linux absolute symlinks under `opt/bluesky-bot/` could not be created as Windows symlinks (privilege). Recreated as **file copies** of staging targets (`.env`, `bot_config.json`, memory, ledger, audit, heartbeat).  
`venv/bin/python3` → `/usr/bin/python3` recorded as `opt/bluesky-bot/venv/bin/python3.SYMLINK.txt` (not portable).

## Security

- `.env` present under `etc/bluesky-bot/` (and opt copy) — **plaintext secrets on disk; do not commit**
- `.gitignore` covers `.env`, `var/`, `venv/`; export-specific entries reinforced
- No Amnezia/VPN paths in staging trees
- Do not paste env values into `ai_docs`

## Next

- ✅ **Completed** — MIG-008/009 done: local verified; bluesky-bot purged from Paris; VPN untouched
- Local export retained at `G:\cursor\BlueSky-bot` (not deleted)
- Report: `G:\cursor\париж+варшава\ai_docs\develop\reports\2026-09-15-paris-bluesky-local-export.md`
