#!/usr/bin/env bash

# BlueSky Bot installer (APT-first)
set -euo pipefail

REPO_URL="https://olgshow.github.io/BlueSky-bot/apt"
LIST_FILE="/etc/apt/sources.list.d/bluesky-bot.list"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok() { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err() { echo -e "${RED}[x]${NC} $*"; }

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
BlueSky Bot installer (Ubuntu, APT-first)

Usage:
  curl -sSL https://raw.githubusercontent.com/OLGShow/BlueSky-bot/main/install.sh | bash

Options:
  --legacy   Run the old git+venv installer flow (deprecated)
  -h, --help Show this help
EOF
  exit 0
fi

# Optional legacy path (kept only for compatibility)
if [[ "${1:-}" == "--legacy" ]]; then
  warn "Legacy installer path is deprecated. Use APT default flow."
  exec bash -lc "echo 'Legacy mode disabled in this installer version.'; exit 1"
fi

if [[ $EUID -eq 0 ]]; then
  err "Run as a regular sudo user, not root."
  exit 1
fi

if ! grep -qi "ubuntu" /etc/os-release 2>/dev/null; then
  err "This installer targets Ubuntu."
  exit 1
fi

ok "Configuring APT repository"
echo "deb [trusted=yes] ${REPO_URL} stable main" | sudo tee "${LIST_FILE}" >/dev/null

ok "Installing package"
sudo apt update
sudo apt install -y bluesky-bot

echo
ok "Installation complete"
echo "Check service status:"
echo "  systemctl status bluesky-bot --no-pager"
echo
echo "If credentials are not configured yet:"
echo "  sudo nano /etc/bluesky-bot/.env"
echo "  sudo systemctl restart bluesky-bot"
echo
echo "Update command:"
echo "  sudo apt update && sudo apt upgrade"