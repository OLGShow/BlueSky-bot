#!/bin/bash
#
# Build a .deb package for bluesky-bot.
# Usage:  bash packaging/build-deb.sh [version]
# Output: packaging/dist/bluesky-bot_<version>_all.deb
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

VERSION="${1:-$(grep '^Version:' "$SCRIPT_DIR/deb/control" | awk '{print $2}')}"
PKG="bluesky-bot"
STAGE="$SCRIPT_DIR/_stage"
DIST="$SCRIPT_DIR/dist"

rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN"
mkdir -p "$STAGE/opt/bluesky-bot"
mkdir -p "$STAGE/etc/bluesky-bot"
mkdir -p "$STAGE/var/lib/bluesky-bot"
mkdir -p "$STAGE/etc/systemd/system"
mkdir -p "$DIST"
chmod 0755 "$STAGE/DEBIAN"

# --- DEBIAN metadata ---
sed "s/^Version:.*/Version: ${VERSION}/" "$SCRIPT_DIR/deb/control" > "$STAGE/DEBIAN/control"
cp "$SCRIPT_DIR/deb/conffiles" "$STAGE/DEBIAN/conffiles"
cp "$SCRIPT_DIR/deb/postinst"  "$STAGE/DEBIAN/postinst"
cp "$SCRIPT_DIR/deb/prerm"     "$STAGE/DEBIAN/prerm"
cp "$SCRIPT_DIR/deb/postrm"    "$STAGE/DEBIAN/postrm"
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/prerm" "$STAGE/DEBIAN/postrm"

# --- Application code ---
# app/ modules are the source of truth (SoT). Stage stays flat under /opt/bluesky-bot/;
# keep this list in sync with packaging/sync-opt-from-sot.sh.
APP_DIR="$REPO_ROOT/app"
PYFILES=(
    bluesky_bot_v2.py
    ai_improvements.py
    bluesky_post_formatter.py
    bluesky_rich_posts.py
    bot_cycle.py
    bot_learning_module.py
    bot_monitor.py
    content_ports.py
    content_publish_state.py
    content_service.py
    daily_reporting.py
    dynamic_content_system.py
    engagement_cache_sync.py
    engagement_ports.py
    engagement_service.py
    follow_strategy.py
    growth_engine.py
    heartbeat_monitor.py
    post_strategies.py
    http_session.py
    log_sanitizer.py
    openrouter_adapter.py
    pollinations_adapter.py
    quality_pipeline.py
    relevance_scoring.py
    resilience_service.py
    rss_content.py
    rss_source_manager.py
    smart_engagement.py
    state_service.py
    strategy_learning.py
    url_safety.py
    verify_bot.py
)

for f in "${PYFILES[@]}"; do
    [ -f "$APP_DIR/$f" ] && cp "$APP_DIR/$f" "$STAGE/opt/bluesky-bot/"
done

# strategies/ package (STRAT-002+) under /opt/bluesky-bot/strategies/
if [ -d "$APP_DIR/strategies" ]; then
    mkdir -p "$STAGE/opt/bluesky-bot/strategies"
    for f in "$APP_DIR/strategies"/*.py; do
        [ -f "$f" ] && cp "$f" "$STAGE/opt/bluesky-bot/strategies/"
    done
fi

cp "$REPO_ROOT/requirements.txt" "$STAGE/opt/bluesky-bot/"
cp "$REPO_ROOT/env.example"       "$STAGE/opt/bluesky-bot/"
cp "$REPO_ROOT/bot_config.json"   "$STAGE/opt/bluesky-bot/"

# Conffiles must exist in package payload for dpkg-deb
cp "$REPO_ROOT/env.example" "$STAGE/etc/bluesky-bot/.env"
cp "$REPO_ROOT/bot_config.json" "$STAGE/etc/bluesky-bot/bot_config.json"

# --- systemd unit ---
# SoT: systemd/bluesky-bot.service
# etc/systemd/system/bluesky-bot.service is a synced copy for repo layout reference.
UNIT_SOT="$REPO_ROOT/systemd/bluesky-bot.service"
cp "$UNIT_SOT" "$STAGE/etc/systemd/system/bluesky-bot.service"

# --- Build ---
DEB_FILE="$DIST/${PKG}_${VERSION}_all.deb"
dpkg-deb --build "$STAGE" "$DEB_FILE"

rm -rf "$STAGE"

echo ""
echo "Built: $DEB_FILE"
echo "Size:  $(du -h "$DEB_FILE" | cut -f1)"
