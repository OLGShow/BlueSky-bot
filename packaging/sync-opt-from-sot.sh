#!/bin/bash
#
# SYNC: copy runtime artifacts from SoT → opt/bluesky-bot/
#
# Direction is ONE-WAY only: SoT → opt. Never copy opt back into SoT.
# Do NOT copy secrets (.env, session.json, credentials, bot_memory.*, etc.).
#
# SoT mapping:
#   app/*.py          — Python runtime modules (listed in PYFILES)
#   root env.example  — example env template (this script)
#   root requirements.txt / bot_config.json — already mirrored in opt/; also
#     copied by packaging/build-deb.sh into the deb stage (no drift expected)
#
# packaging/_stage/ is ephemeral (created/destroyed by build-deb.sh from app/);
# this script keeps the tracked deploy mirror under opt/bluesky-bot/ aligned.
# Deploy layout stays flat under /opt/bluesky-bot/ (systemd WorkingDirectory).
#
# Usage:  bash packaging/sync-opt-from-sot.sh
# Idempotent: re-running overwrites opt copies with SoT content.
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
    bot_cycle.py
    bot_learning_module.py
    bot_monitor.py
    content_ports.py
    content_service.py
    dynamic_content_system.py
    engagement_ports.py
    engagement_service.py
    growth_engine.py
    post_strategies.py
    http_session.py
    log_sanitizer.py
    openrouter_adapter.py
    pollinations_adapter.py
    quality_pipeline.py
    resilience_service.py
    rss_source_manager.py
    state_service.py
    strategy_learning.py
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

# strategies/ package (STRAT-002+) — keep import path ``strategies.*`` under deploy root
STRATEGIES_SRC="$APP_DIR/strategies"
STRATEGIES_DST="$OPT_DIR/strategies"
if [[ ! -d "$STRATEGIES_SRC" ]]; then
    echo "WARN: missing SoT package: app/strategies/" >&2
    missing=$((missing + 1))
else
    mkdir -p "$STRATEGIES_DST"
    for f in "$STRATEGIES_SRC"/*.py; do
        [[ -f "$f" ]] || continue
        base="$(basename "$f")"
        cp "$f" "$STRATEGIES_DST/$base"
        echo "synced: strategies/$base"
        synced=$((synced + 1))
    done
fi

# Root SoT for env template (not under app/)
ENV_SRC="$REPO_ROOT/env.example"
if [[ ! -f "$ENV_SRC" ]]; then
    echo "WARN: missing SoT: env.example" >&2
    missing=$((missing + 1))
else
    cp "$ENV_SRC" "$OPT_DIR/env.example"
    echo "synced: env.example (root SoT)"
    synced=$((synced + 1))
fi

echo ""
echo "SoT: app/ (py) + root env.example. Synced $synced file(s) → opt/bluesky-bot/"
echo "Note: requirements.txt / bot_config.json are root SoT; opt mirror + build-deb.sh already copy them."
if [[ "$missing" -gt 0 ]]; then
    echo "WARN: $missing listed file(s) missing from SoT" >&2
    exit 1
fi
