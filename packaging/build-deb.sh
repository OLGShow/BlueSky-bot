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
    log_sanitizer.py
    pollinations_adapter.py
    resilience_service.py
    rss_source_manager.py
    state_service.py
    verify_bot.py
)

for f in "${PYFILES[@]}"; do
    [ -f "$REPO_ROOT/$f" ] && cp "$REPO_ROOT/$f" "$STAGE/opt/bluesky-bot/"
done

cp "$REPO_ROOT/requirements.txt" "$STAGE/opt/bluesky-bot/"
cp "$REPO_ROOT/env.example"       "$STAGE/opt/bluesky-bot/"
cp "$REPO_ROOT/bot_config.json"   "$STAGE/opt/bluesky-bot/"

# Conffiles must exist in package payload for dpkg-deb
cp "$REPO_ROOT/env.example" "$STAGE/etc/bluesky-bot/.env"
cp "$REPO_ROOT/bot_config.json" "$STAGE/etc/bluesky-bot/bot_config.json"

# --- systemd unit (patched for package paths) ---
cat > "$STAGE/etc/systemd/system/bluesky-bot.service" << 'UNIT'
[Unit]
Description=BlueSky Bot - Autonomous AI Social Media Bot
Documentation=https://github.com/OLGShow/BlueSky-bot
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=bluesky-bot
Group=bluesky-bot
WorkingDirectory=/opt/bluesky-bot
EnvironmentFile=/etc/bluesky-bot/.env

ExecStart=/opt/bluesky-bot/venv/bin/python /opt/bluesky-bot/bluesky_bot_v2.py

Restart=always
RestartSec=10
StartLimitBurst=5
StartLimitInterval=60

StandardOutput=journal
StandardError=journal
SyslogIdentifier=bluesky-bot

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/bluesky-bot /var/lib/bluesky-bot /etc/bluesky-bot
MemoryMax=512M

KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
UNIT

# --- Build ---
DEB_FILE="$DIST/${PKG}_${VERSION}_all.deb"
dpkg-deb --build "$STAGE" "$DEB_FILE"

rm -rf "$STAGE"

echo ""
echo "Built: $DEB_FILE"
echo "Size:  $(du -h "$DEB_FILE" | cut -f1)"
