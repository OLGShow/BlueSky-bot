#!/bin/bash
#
# SYNC: copy runtime Python modules from repo root (SoT) → opt/bluesky-bot/
#
# Direction is ONE-WAY only: root → opt. Never copy opt back into root.
# Do NOT copy secrets (.env, session.json, credentials, bot_memory.*, etc.).
#
# packaging/_stage/ is ephemeral (created/destroyed by build-deb.sh from root);
# this script keeps the tracked deploy mirror under opt/bluesky-bot/ aligned.
#
# Usage:  bash packaging/sync-opt-from-sot.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
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
    src="$REPO_ROOT/$f"
    if [[ ! -f "$src" ]]; then
        echo "WARN: missing SoT module: $f" >&2
        missing=$((missing + 1))
        continue
    fi
    cp "$src" "$OPT_DIR/$f"
    echo "synced: $f"
    synced=$((synced + 1))
done

echo ""
echo "Root is SoT. Synced $synced module(s) → opt/bluesky-bot/"
if [[ "$missing" -gt 0 ]]; then
    echo "WARN: $missing listed module(s) missing from root" >&2
    exit 1
fi
