#!/bin/bash
#
# SYNC: copy runtime Python modules from app/ (SoT) → opt/bluesky-bot/
#
# Direction is ONE-WAY only: app/ → opt. Never copy opt back into app/.
# Do NOT copy secrets (.env, session.json, credentials, bot_memory.*, etc.).
#
# packaging/_stage/ is ephemeral (created/destroyed by build-deb.sh from app/);
# this script keeps the tracked deploy mirror under opt/bluesky-bot/ aligned.
# Deploy layout stays flat under /opt/bluesky-bot/ (systemd WorkingDirectory).
#
# Usage:  bash packaging/sync-opt-from-sot.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="$REPO_ROOT/app"
OPT_DIR="$REPO_ROOT/opt/bluesky-bot"

# Must match packaging/build-deb.sh PYFILES (runtime modules only).
PYFILES=(
    bluesky_bot_v2.py
    ai_improvements.py
    bluesky_post_formatter.py
    bluesky_rich_posts.py
    bot_learning_module.py
    bot_monitor.py
    content_service.py
    dynamic_content_system.py
    engagement_service.py
    growth_engine.py
    http_session.py
    log_sanitizer.py
    openrouter_adapter.py
    pollinations_adapter.py
    resilience_service.py
    rss_source_manager.py
    state_service.py
    url_safety.py
    verify_bot.py
)

mkdir -p "$OPT_DIR"

synced=0
missing=0
for f in "${PYFILES[@]}"; do
    src="$APP_DIR/$f"
    if [[ ! -f "$src" ]]; then
        echo "WARN: missing SoT module: app/$f" >&2
        missing=$((missing + 1))
        continue
    fi
    cp "$src" "$OPT_DIR/$f"
    echo "synced: $f"
    synced=$((synced + 1))
done

echo ""
echo "app/ is SoT. Synced $synced module(s) → opt/bluesky-bot/"
if [[ "$missing" -gt 0 ]]; then
    echo "WARN: $missing listed module(s) missing from app/" >&2
    exit 1
fi
