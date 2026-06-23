#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${SKYWEAVER_INSTALL_DIR:-/opt/skyweaver}"
BACKUP_DIR="${SKYWEAVER_BACKUP_DIR:-/var/lib/skyweaver/backups/$(date +%Y%m%d-%H%M%S)}"
SERVICE_USER="${SKYWEAVER_SERVICE_USER:-skyweaver}"
HARDWARE_GROUPS="${SKYWEAVER_HARDWARE_GROUPS:-video,render,input,gpio,i2c,spi}"

grant_hardware_groups() {
  local group
  if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    return
  fi
  IFS="," read -r -a groups <<<"$HARDWARE_GROUPS"
  for group in "${groups[@]}"; do
    if getent group "$group" >/dev/null 2>&1; then
      usermod -a -G "$group" "$SERVICE_USER"
    fi
  done
}

if [[ "${EUID}" -ne 0 ]]; then echo "Please run with sudo"; exit 1; fi
mkdir -p "$BACKUP_DIR"
systemctl stop skyweaver.target || true
cp -a /etc/skyweaver "$BACKUP_DIR/config" 2>/dev/null || true
cp -a /var/lib/skyweaver/skyweaver.db "$BACKUP_DIR/skyweaver.db" 2>/dev/null || true
grant_hardware_groups
rsync -a --delete --exclude .git --exclude node_modules --exclude data --exclude logs "$ROOT_DIR/" "$INSTALL_DIR/"
python3 -m venv "$INSTALL_DIR/backend/.venv"
"$INSTALL_DIR/backend/.venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/backend/.venv/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt"
npm ci --prefix "$INSTALL_DIR"
npm run build --prefix "$INSTALL_DIR"
rsync -a --delete "$INSTALL_DIR/dist/" /var/lib/skyweaver/web/
cp "$INSTALL_DIR/scripts/systemd/"*.service "$INSTALL_DIR/scripts/systemd/skyweaver.target" /etc/systemd/system/
systemctl daemon-reload
systemctl restart skyweaver.target
echo "Upgrade complete. Backup: $BACKUP_DIR"
