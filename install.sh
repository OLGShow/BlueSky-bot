#!/usr/bin/env bash

# BlueSky Bot installer (APT-first)
set -euo pipefail

REPO_URL="https://olgshow.github.io/BlueSky-bot/apt"
LIST_FILE="/etc/apt/sources.list.d/bluesky-bot.list"
ENV_FILE="/etc/bluesky-bot/.env"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok() { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err() { echo -e "${RED}[x]${NC} $*"; }

can_prompt_tty() {
  [[ -r /dev/tty && -w /dev/tty ]]
}

set_env_var() {
  local key="$1"
  local value="$2"
  local escaped
  escaped="$(printf '%s' "$value" | sed 's/[&|]/\\&/g')"
  if sudo grep -q "^${key}=" "${ENV_FILE}" 2>/dev/null; then
    sudo sed -i "s|^${key}=.*|${key}=${escaped}|" "${ENV_FILE}"
  else
    echo "${key}=${value}" | sudo tee -a "${ENV_FILE}" >/dev/null
  fi
}

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

if sudo test -f "${ENV_FILE}"; then
  if sudo grep -Eq "your-bot\.bsky\.social|your-app-password" "${ENV_FILE}"; then
    if can_prompt_tty; then
      echo
      warn "Credentials are not configured yet. Let's set them now."
      read -r -p "BLUESKY_HANDLE (example: my-bot.bsky.social): " BS_HANDLE < /dev/tty
      read -r -s -p "BLUESKY_PASSWORD (app password): " BS_PASSWORD < /dev/tty
      echo > /dev/tty

      if [[ -n "${BS_HANDLE}" && -n "${BS_PASSWORD}" ]]; then
        set_env_var "BLUESKY_HANDLE" "${BS_HANDLE}"
        set_env_var "BLUESKY_PASSWORD" "${BS_PASSWORD}"
        sudo chown bluesky-bot:bluesky-bot "${ENV_FILE}" 2>/dev/null || true
        sudo chmod 600 "${ENV_FILE}" 2>/dev/null || true
        sudo systemctl restart bluesky-bot
        ok "Credentials saved and service restarted"
      else
        warn "Credentials skipped. Configure manually:"
        echo "  sudo nano ${ENV_FILE}"
        echo "  sudo systemctl restart bluesky-bot"
      fi
    else
      warn "No interactive terminal available. Configure credentials manually:"
      echo "  sudo nano ${ENV_FILE}"
      echo "  sudo systemctl restart bluesky-bot"
    fi
  fi
fi

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