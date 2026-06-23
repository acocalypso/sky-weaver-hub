#!/usr/bin/env bash
set -euo pipefail

OUT="${SKYWEAVER_SUPPORT_OUT:-/tmp/skyweaver-support-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT"
{
  date -Is
  uname -a
  cat /etc/os-release 2>/dev/null || true
  tr -d '\0' </proc/device-tree/model 2>/dev/null || true
} >"$OUT/system.txt"
(rpicam-hello --list-cameras || libcamera-hello --list-cameras || true) >"$OUT/cameras.txt" 2>&1
(v4l2-ctl --list-devices || true) >"$OUT/v4l2.txt" 2>&1
(gphoto2 --auto-detect || true) >"$OUT/gphoto2.txt" 2>&1
(systemctl status skyweaver.target skyweaver-api skyweaver-capture skyweaver-worker || true) >"$OUT/services.txt" 2>&1
(journalctl -u skyweaver-api -u skyweaver-capture -u skyweaver-worker -n 300 --no-pager || true) >"$OUT/journal.txt" 2>&1
(df -h; du -sh /var/lib/skyweaver 2>/dev/null || true) >"$OUT/disk.txt"
if [[ -f /etc/skyweaver/skyweaver.env ]]; then sed -E 's/(SECRET|PASSWORD|KEY)=.*/\1=REDACTED/g' /etc/skyweaver/skyweaver.env >"$OUT/config-redacted.env"; fi
(curl -fsS http://127.0.0.1:8765/api/v1/health || true) >"$OUT/api-health.json"
tar -czf "$OUT.tar.gz" -C "$(dirname "$OUT")" "$(basename "$OUT")"
echo "$OUT.tar.gz"
