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
DEFAULT_ADMIN_PASSWORD="skyweaver-change-me"

SETUP_ADMIN_USERNAME=""
SETUP_ADMIN_PASSWORD=""
SETUP_OBSERVATORY_NAME=""
SETUP_LATITUDE=""
SETUP_LONGITUDE=""
SETUP_TIMEZONE=""
SETUP_CAMERA_ADAPTER=""
SETUP_PUBLIC_PAGE_ENABLED=""
SETUP_FIRST_SETUP_REQUIRED=""

run() {
  echo "+ $*"
  if [[ "$DRY_RUN" != "1" ]]; then "$@"; fi
}

is_interactive() {
  [[ -t 0 && -t 1 && "${SKYWEAVER_NONINTERACTIVE:-0}" != "1" ]]
}

prompt_text() {
  local prompt="$1"
  local default="$2"
  local value
  read -r -p "$prompt [$default]: " value
  printf "%s" "${value:-$default}"
}

prompt_password() {
  local first second
  while true; do
    read -r -s -p "Admin password [leave blank for bootstrap default]: " first
    echo
    if [[ -z "$first" ]]; then
      printf "%s" "$DEFAULT_ADMIN_PASSWORD"
      return
    fi
    read -r -s -p "Confirm admin password: " second
    echo
    if [[ "$first" == "$second" ]]; then
      printf "%s" "$first"
      return
    fi
    echo "Passwords did not match."
  done
}

prompt_yes_no() {
  local prompt="$1"
  local default="$2"
  local value
  read -r -p "$prompt [$default]: " value
  value="${value:-$default}"
  case "${value,,}" in
    y|yes|true|1) printf "1" ;;
    *) printf "0" ;;
  esac
}

default_timezone() {
  if command -v timedatectl >/dev/null 2>&1; then
    timedatectl show -p Timezone --value 2>/dev/null || true
  elif [[ -f /etc/timezone ]]; then
    head -n 1 /etc/timezone
  fi
}

collect_setup_answers() {
  SETUP_ADMIN_USERNAME="${SKYWEAVER_SETUP_ADMIN_USERNAME:-${SKYWEAVER_ADMIN_USERNAME:-admin}}"
  SETUP_ADMIN_PASSWORD="${SKYWEAVER_SETUP_ADMIN_PASSWORD:-${SKYWEAVER_ADMIN_PASSWORD:-$DEFAULT_ADMIN_PASSWORD}}"
  SETUP_OBSERVATORY_NAME="${SKYWEAVER_OBSERVATORY_NAME:-Sky Weaver Observatory}"
  SETUP_LATITUDE="${SKYWEAVER_OBSERVATORY_LATITUDE:-0}"
  SETUP_LONGITUDE="${SKYWEAVER_OBSERVATORY_LONGITUDE:-0}"
  SETUP_TIMEZONE="${SKYWEAVER_OBSERVATORY_TIMEZONE:-$(default_timezone)}"
  SETUP_TIMEZONE="${SETUP_TIMEZONE:-UTC}"
  SETUP_CAMERA_ADAPTER="${SKYWEAVER_PRIMARY_CAMERA_ADAPTER:-mock}"
  SETUP_PUBLIC_PAGE_ENABLED="${SKYWEAVER_PUBLIC_PAGE_ENABLED:-1}"

  if is_interactive; then
    echo
    echo "First setup"
    SETUP_ADMIN_USERNAME="$(prompt_text "Admin username" "$SETUP_ADMIN_USERNAME")"
    SETUP_ADMIN_PASSWORD="$(prompt_password)"
    SETUP_OBSERVATORY_NAME="$(prompt_text "Observatory name" "$SETUP_OBSERVATORY_NAME")"
    SETUP_LATITUDE="$(prompt_text "Observatory latitude" "$SETUP_LATITUDE")"
    SETUP_LONGITUDE="$(prompt_text "Observatory longitude" "$SETUP_LONGITUDE")"
    SETUP_TIMEZONE="$(prompt_text "Timezone" "$SETUP_TIMEZONE")"
    SETUP_CAMERA_ADAPTER="$(prompt_text "Primary camera adapter (mock, rpicam, libcamera, gphoto2, v4l2, zwo, indi, custom_command)" "$SETUP_CAMERA_ADAPTER")"
    SETUP_PUBLIC_PAGE_ENABLED="$(prompt_yes_no "Enable public sky page" "Y")"
  fi

  case "${SETUP_PUBLIC_PAGE_ENABLED,,}" in
    y|yes|true|1) SETUP_PUBLIC_PAGE_ENABLED="1" ;;
    *) SETUP_PUBLIC_PAGE_ENABLED="0" ;;
  esac
  if [[ "$SETUP_ADMIN_PASSWORD" == "$DEFAULT_ADMIN_PASSWORD" ]]; then
    SETUP_FIRST_SETUP_REQUIRED="1"
  else
    SETUP_FIRST_SETUP_REQUIRED="0"
  fi
}

env_line() {
  local escaped
  escaped="${2//\'/\'\\\'\'}"
  printf "%s='%s'\n" "$1" "$escaped"
}

hash_admin_password() {
  SKYWEAVER_SETUP_PASSWORD="$1" PYTHONPATH="$INSTALL_DIR/backend" "$INSTALL_DIR/backend/.venv/bin/python" - <<'PY'
import os

from skyweaver.security import hash_password

print(hash_password(os.environ["SKYWEAVER_SETUP_PASSWORD"]))
PY
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
  run apt-get install -y git curl jq nodejs npm python3 python3-venv python3-pip ffmpeg imagemagick v4l-utils gphoto2 sqlite3 build-essential
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
  local secret admin_password_hash
  if [[ -f "$CONFIG_DIR/skyweaver.env" ]]; then
    echo "Keeping existing $CONFIG_DIR/skyweaver.env"
    return
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "+ install -m 640 skyweaver.env $CONFIG_DIR/skyweaver.env"
    echo "+ chown $CONFIG_OWNER:$SERVICE_GROUP $CONFIG_DIR/skyweaver.env"
    return
  fi
  collect_setup_answers
  secret="$(openssl rand -hex 32 2>/dev/null || date +%s%N)"
  admin_password_hash="$(hash_admin_password "$SETUP_ADMIN_PASSWORD")"
  if [[ ! -f "$CONFIG_DIR/skyweaver.env" ]]; then
    {
      env_line SKYWEAVER_ENV production
      env_line SKYWEAVER_HOST 0.0.0.0
      env_line SKYWEAVER_PORT 8765
      env_line SKYWEAVER_SECRET_KEY "$secret"
      env_line SKYWEAVER_DATA_DIR "$DATA_DIR"
      env_line SKYWEAVER_CONFIG_DIR "$CONFIG_DIR"
      env_line SKYWEAVER_LOG_DIR "$LOG_DIR"
      env_line SKYWEAVER_DB "$DATA_DIR/skyweaver.db"
      env_line SKYWEAVER_ADMIN_USERNAME "$SETUP_ADMIN_USERNAME"
      env_line SKYWEAVER_ADMIN_PASSWORD_HASH "$admin_password_hash"
      env_line SKYWEAVER_OBSERVATORY_NAME "$SETUP_OBSERVATORY_NAME"
      env_line SKYWEAVER_OBSERVATORY_LATITUDE "$SETUP_LATITUDE"
      env_line SKYWEAVER_OBSERVATORY_LONGITUDE "$SETUP_LONGITUDE"
      env_line SKYWEAVER_OBSERVATORY_TIMEZONE "$SETUP_TIMEZONE"
      env_line SKYWEAVER_PRIMARY_CAMERA_ADAPTER "$SETUP_CAMERA_ADAPTER"
      env_line SKYWEAVER_PUBLIC_PAGE_ENABLED "$SETUP_PUBLIC_PAGE_ENABLED"
      env_line SKYWEAVER_FIRST_SETUP_REQUIRED "$SETUP_FIRST_SETUP_REQUIRED"
    } >"$CONFIG_DIR/skyweaver.env"
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
  if [[ -n "$SETUP_ADMIN_USERNAME" && "$SETUP_FIRST_SETUP_REQUIRED" == "0" ]]; then
    echo "Admin login: $SETUP_ADMIN_USERNAME / configured during setup"
  else
    echo "Bootstrap login: admin / skyweaver-change-me"
  fi
}

main "$@"
