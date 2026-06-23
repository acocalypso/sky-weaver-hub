#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${SKYWEAVER_INSTALL_DIR:-/opt/skyweaver}"
BACKUP_DIR="${SKYWEAVER_BACKUP_DIR:-/var/lib/skyweaver/backups/$(date +%Y%m%d-%H%M%S)}"

if [[ "${EUID}" -ne 0 ]]; then echo "Please run with sudo"; exit 1; fi
mkdir -p "$BACKUP_DIR"
systemctl stop skyweaver.target || true
cp -a /etc/skyweaver "$BACKUP_DIR/config" 2>/dev/null || true
cp -a /var/lib/skyweaver/skyweaver.db "$BACKUP_DIR/skyweaver.db" 2>/dev/null || true
rsync -a --delete --exclude .git --exclude node_modules --exclude data --exclude logs "$ROOT_DIR/" "$INSTALL_DIR/"
"$INSTALL_DIR/backend/.venv/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt"
npm ci --prefix "$INSTALL_DIR"
npm run build --prefix "$INSTALL_DIR"
rsync -a --delete "$INSTALL_DIR/dist/" /var/lib/skyweaver/web/
cp "$INSTALL_DIR/scripts/systemd/"*.service "$INSTALL_DIR/scripts/systemd/skyweaver.target" /etc/systemd/system/
systemctl daemon-reload
systemctl restart skyweaver.target
echo "Upgrade complete. Backup: $BACKUP_DIR"
