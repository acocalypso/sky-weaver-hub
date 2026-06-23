#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${SKYWEAVER_INSTALL_DIR:-/opt/skyweaver}"
CONFIG_DIR="${SKYWEAVER_CONFIG_DIR:-/etc/skyweaver}"
DATA_DIR="${SKYWEAVER_DATA_DIR:-/var/lib/skyweaver}"
LOG_DIR="${SKYWEAVER_LOG_DIR:-/var/log/skyweaver}"
SYSTEMD_DIR="${SKYWEAVER_SYSTEMD_DIR:-/etc/systemd/system}"
SERVICE_USER="${SKYWEAVER_SERVICE_USER:-skyweaver}"
SERVICE_GROUP="${SKYWEAVER_SERVICE_GROUP:-skyweaver}"
CONFIG_OWNER="${SKYWEAVER_CONFIG_OWNER:-root}"
DRY_RUN="${SKYWEAVER_DRY_RUN:-0}"
ALLOW_NON_ROOT="${SKYWEAVER_ALLOW_NON_ROOT:-0}"

run() {
  echo "+ $*"
  if [[ "$DRY_RUN" != "1" ]]; then "$@"; fi
}

need_root() {
  if [[ "$DRY_RUN" == "1" || "$ALLOW_NON_ROOT" == "1" ]]; then
    return
  fi
  if [[ "${EUID}" -ne 0 ]]; then
    echo "Please run with sudo: sudo ./install.sh"
    exit 1
  fi
}

detect_os() {
  if [[ -f /etc/os-release ]]; then
    # shellcheck source=/dev/null
    . /etc/os-release
  else
    PRETTY_NAME="Unknown Linux"
    ID="unknown"
    VERSION_CODENAME=""
  fi
  echo "Detected ${PRETTY_NAME:-Linux} on $(uname -m)"
  if grep -qi raspberry /proc/device-tree/model 2>/dev/null; then
    echo "Raspberry Pi: $(tr -d '\0' </proc/device-tree/model)"
    if [[ "${VERSION_CODENAME:-}" != "bookworm" ]]; then
      echo "Warning: Raspberry Pi OS Bookworm is the primary supported target."
    fi
  elif [[ "${ID:-}" != "debian" && "${ID:-}" != "ubuntu" ]]; then
    echo "Warning: non-Debian/Ubuntu hosts are development-only targets."
  fi
}

install_packages() {
  run apt-get update
  run apt-get install -y git curl jq python3 python3-venv python3-pip ffmpeg imagemagick v4l-utils gphoto2 sqlite3 build-essential
  if [[ "$DRY_RUN" == "1" ]]; then
    run apt-get install -y rpicam-apps
    echo "+ apt-get install -y libcamera-apps # fallback if rpicam-apps is unavailable"
    return
  fi
  if apt-cache show rpicam-apps >/dev/null 2>&1; then run apt-get install -y rpicam-apps; else run apt-get install -y libcamera-apps || true; fi
}

create_user_dirs() {
  if ! id "$SERVICE_USER" >/dev/null 2>&1; then run useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"; fi
  run mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$DATA_DIR" "$DATA_DIR/images" "$DATA_DIR/thumbnails" "$DATA_DIR/products" "$LOG_DIR"
  run chown -R "$SERVICE_USER:$SERVICE_GROUP" "$DATA_DIR" "$LOG_DIR"
}

copy_code() {
  run rsync -a --delete --exclude .git --exclude node_modules --exclude data --exclude logs "$ROOT_DIR/" "$INSTALL_DIR/"
}

build_backend() {
  run python3 -m venv "$INSTALL_DIR/backend/.venv"
  run "$INSTALL_DIR/backend/.venv/bin/pip" install --upgrade pip
  run "$INSTALL_DIR/backend/.venv/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt"
}

build_frontend() {
  if [[ -f "$INSTALL_DIR/package.json" || ( "$DRY_RUN" == "1" && -f "$ROOT_DIR/package.json" ) ]]; then
    run npm ci --prefix "$INSTALL_DIR"
    run npm run build --prefix "$INSTALL_DIR"
    run mkdir -p "$DATA_DIR/web"
    run rsync -a --delete "$INSTALL_DIR/dist/" "$DATA_DIR/web/"
    run chown -R "$SERVICE_USER:$SERVICE_GROUP" "$DATA_DIR/web"
  fi
}

write_config() {
  local secret
  if [[ -f "$CONFIG_DIR/skyweaver.env" ]]; then
    echo "Keeping existing $CONFIG_DIR/skyweaver.env"
    return
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "+ install -m 640 skyweaver.env $CONFIG_DIR/skyweaver.env"
    echo "+ chown $CONFIG_OWNER:$SERVICE_GROUP $CONFIG_DIR/skyweaver.env"
    return
  fi
  secret="$(openssl rand -hex 32 2>/dev/null || date +%s%N)"
  if [[ ! -f "$CONFIG_DIR/skyweaver.env" ]]; then
    cat >"$CONFIG_DIR/skyweaver.env" <<EOF
SKYWEAVER_ENV=production
SKYWEAVER_HOST=0.0.0.0
SKYWEAVER_PORT=8765
SKYWEAVER_SECRET_KEY=$secret
SKYWEAVER_DATA_DIR=$DATA_DIR
SKYWEAVER_CONFIG_DIR=$CONFIG_DIR
SKYWEAVER_LOG_DIR=$LOG_DIR
SKYWEAVER_DB=$DATA_DIR/skyweaver.db
SKYWEAVER_ADMIN_USERNAME=admin
EOF
    chmod 640 "$CONFIG_DIR/skyweaver.env"
    chown "$CONFIG_OWNER:$SERVICE_GROUP" "$CONFIG_DIR/skyweaver.env"
  fi
}

install_systemd() {
  run mkdir -p "$SYSTEMD_DIR"
  run cp "$INSTALL_DIR/scripts/systemd/"*.service "$INSTALL_DIR/scripts/systemd/skyweaver.target" "$SYSTEMD_DIR/"
  run systemctl daemon-reload
  run systemctl enable skyweaver.target skyweaver-api.service skyweaver-capture.service skyweaver-worker.service
  run systemctl restart skyweaver.target
}

main() {
  need_root
  detect_os
  install_packages
  create_user_dirs
  copy_code
  build_backend
  build_frontend
  write_config
  install_systemd
  echo
  echo "Sky Weaver Hub installed."
  echo "Admin UI: http://skyweaver.local:8765/"
  echo "Public sky page: http://skyweaver.local:8765/public"
  echo "API docs: http://skyweaver.local:8765/api/docs"
  echo "Bootstrap login: admin / skyweaver-change-me"
}

main "$@"
