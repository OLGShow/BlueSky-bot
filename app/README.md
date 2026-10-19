# Application source of truth (SoT)

Runtime Python modules live here. Packaging copies them **flat** into
`opt/bluesky-bot/` / `/opt/bluesky-bot` for systemd and deb installs.

```bash
# Sync deploy mirror from SoT
bash packaging/sync-opt-from-sot.sh

# Local verify (root shim)
python verify_bot.py --smoke
# or directly:
python app/verify_bot.py --smoke
```
