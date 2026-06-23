#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then echo "Please run with sudo"; exit 1; fi
read -r -p "Remove Sky Weaver services? [y/N] " yn
[[ "$yn" == "y" || "$yn" == "Y" ]] || exit 0
systemctl stop skyweaver.target || true
systemctl disable skyweaver.target skyweaver-api.service skyweaver-capture.service skyweaver-worker.service || true
rm -f /etc/systemd/system/skyweaver.target /etc/systemd/system/skyweaver-api.service /etc/systemd/system/skyweaver-capture.service /etc/systemd/system/skyweaver-worker.service
systemctl daemon-reload
read -r -p "Remove images, config, and database too? [y/N] " purge
if [[ "$purge" == "y" || "$purge" == "Y" ]]; then
  rm -rf /opt/skyweaver /etc/skyweaver /var/lib/skyweaver /var/log/skyweaver
else
  rm -rf /opt/skyweaver
fi
echo "Uninstall complete."
