#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${SKYWEAVER_INSTALL_DIR:-/opt/skyweaver}"
CONFIG_DIR="${SKYWEAVER_CONFIG_DIR:-/etc/skyweaver}"
BACKUP_DIR="${SKYWEAVER_BACKUP_DIR:-/var/lib/skyweaver/backups/$(date +%Y%m%d-%H%M%S)}"
SERVICE_USER="${SKYWEAVER_SERVICE_USER:-skyweaver}"
HARDWARE_GROUPS="${SKYWEAVER_HARDWARE_GROUPS:-video,render,input,gpio,i2c,spi}"
SUDOERS_DIR="${SKYWEAVER_SUDOERS_DIR:-/etc/sudoers.d}"
SYSTEMCTL_BIN="${SKYWEAVER_SYSTEMCTL_BIN:-/usr/bin/systemctl}"
ZWO_SDK_INSTALL="${SKYWEAVER_INSTALL_ZWO_SDK:-auto}"
ZWO_SDK_URL="${SKYWEAVER_ZWO_SDK_URL:-}"
ZWO_SDK_DIR="${SKYWEAVER_ZWO_SDK_DIR:-/opt/skyweaver/vendor/zwo}"
PREVIOUS_REQUIREMENTS_FILE="$BACKUP_DIR/backend-requirements.txt"

env_line() {
  local escaped
  escaped="${2//\'/\'\\\'\'}"
  printf "%s='%s'\n" "$1" "$escaped"
}

strip_shell_quotes() {
  local value="$1"
  value="${value%$'\r'}"
  value="${value%\'}"
  value="${value#\'}"
  value="${value%\"}"
  value="${value#\"}"
  printf "%s" "$value"
}

configured_primary_adapter() {
  local config_file="$CONFIG_DIR/skyweaver.env"
  local line
  if [[ -f "$config_file" ]]; then
    line="$(grep -E "^SKYWEAVER_PRIMARY_CAMERA_ADAPTER=" "$config_file" | tail -n 1 || true)"
    if [[ -n "$line" ]]; then
      strip_shell_quotes "${line#*=}"
      return
    fi
  fi
  printf "%s" "${SKYWEAVER_PRIMARY_CAMERA_ADAPTER:-mock}"
}

zwo_sdk_requested() {
  case "${ZWO_SDK_INSTALL,,}" in
    1|true|yes) return 0 ;;
    0|false|no) return 1 ;;
  esac
  [[ "$(configured_primary_adapter)" == "zwo" ]]
}

zwo_sdk_library_available() {
  [[ -n "${SKYWEAVER_ZWO_SDK_LIBRARY:-}" && -f "${SKYWEAVER_ZWO_SDK_LIBRARY:-}" ]] && return 0
  command -v ldconfig >/dev/null 2>&1 && ldconfig -p 2>/dev/null | grep -Fq "libASICamera2.so" && return 0
  [[ -f "$ZWO_SDK_DIR/lib/libASICamera2.so" ]]
}

install_zwo_udev_rules() {
  cat >/etc/udev/rules.d/99-zwo-asi.rules <<'EOF'
SUBSYSTEM=="usb", ATTRS{idVendor}=="03c3", MODE="0666"
EOF
  if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules || true
    udevadm trigger || true
  fi
}

ensure_config_env_line() {
  local key="$1"
  local value="$2"
  local config_file="$CONFIG_DIR/skyweaver.env"
  [[ -f "$config_file" ]] || return
  if ! grep -Eq "^${key}=" "$config_file"; then
    env_line "$key" "$value" >>"$config_file"
  fi
}

select_zwo_library() {
  local root="$1"
  local arch candidate
  arch="$(uname -m)"
  case "$arch" in
    aarch64|arm64) candidate="armv8" ;;
    armv7l|armhf) candidate="armv7" ;;
    x86_64|amd64) candidate="x64" ;;
    i386|i686) candidate="x86" ;;
    *) candidate="" ;;
  esac
  if [[ -n "$candidate" ]]; then
    find "$root" -path "*/lib*/$candidate/libASICamera2.so" -print -quit
  fi
  find "$root" -name libASICamera2.so -print -quit
}

install_zwo_sdk() {
  local tmp archive lib rules
  zwo_sdk_requested || return 0
  apt-get install -y curl unzip ca-certificates
  if ! apt-get install -y libasi; then
    if [[ -z "$ZWO_SDK_URL" ]]; then
      echo "ZWO camera adapter is configured, but Debian package libasi could not be installed."
      echo "Enable Debian non-free and install libasi, or set SKYWEAVER_ZWO_SDK_URL to a ZWO ASI SDK archive."
      exit 1
    fi
    echo "Debian package libasi is unavailable; falling back to SKYWEAVER_ZWO_SDK_URL."
  fi
  install_zwo_udev_rules
  if zwo_sdk_library_available; then
    echo "ZWO ASI SDK library available from Debian libasi or system library path."
    return
  fi
  if [[ -z "$ZWO_SDK_URL" ]]; then
    echo "ZWO camera adapter is configured, but libASICamera2.so was not found after installing libasi."
    echo "Enable Debian non-free and install libasi, or set SKYWEAVER_ZWO_SDK_URL to a ZWO ASI SDK archive."
    exit 1
  fi
  tmp="$(mktemp -d)"
  archive="$tmp/zwo-sdk"
  curl -L "$ZWO_SDK_URL" -o "$archive"
  if unzip -t "$archive" >/dev/null 2>&1; then
    unzip -q "$archive" -d "$tmp/sdk"
  else
    mkdir -p "$tmp/sdk"
    tar -xf "$archive" -C "$tmp/sdk"
  fi
  lib="$(select_zwo_library "$tmp/sdk")"
  if [[ -z "$lib" ]]; then
    echo "Could not find libASICamera2.so in the downloaded ZWO SDK archive."
    exit 1
  fi
  install -d "$ZWO_SDK_DIR/lib"
  install -m 755 "$lib" "$ZWO_SDK_DIR/lib/libASICamera2.so"
  rules="$(find "$tmp/sdk" -name asi.rules -print -quit)"
  if [[ -n "$rules" ]]; then
    install -m 644 "$rules" /etc/udev/rules.d/99-zwo-asi.rules
  fi
  echo "$ZWO_SDK_DIR/lib" >/etc/ld.so.conf.d/skyweaver-zwo.conf
  ldconfig
  ensure_config_env_line SKYWEAVER_ZWO_SDK_LIBRARY "$ZWO_SDK_DIR/lib/libASICamera2.so"
  rm -rf "$tmp"
}

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

install_service_controls() {
  local sudoers_file="$SUDOERS_DIR/skyweaver"
  local sudoers_tmp="$SUDOERS_DIR/skyweaver.tmp"
  local units=(skyweaver.target skyweaver-api.service skyweaver-capture.service skyweaver-worker.service)
  local actions=(start stop restart)
  mkdir -p "$SUDOERS_DIR"
  {
    printf "%s ALL=(root) NOPASSWD:" "$SERVICE_USER"
    local first=1 action unit
    for action in "${actions[@]}"; do
      for unit in "${units[@]}"; do
        if [[ "$first" -eq 1 ]]; then first=0; else printf ","; fi
        printf " %s %s %s" "$SYSTEMCTL_BIN" "$action" "$unit"
        if [[ "$unit" == "skyweaver.target" || "$unit" == "skyweaver-api.service" ]]; then
          printf ", %s --no-block %s %s" "$SYSTEMCTL_BIN" "$action" "$unit"
        fi
      done
    done
    printf "\n"
  } >"$sudoers_tmp"
  chmod 440 "$sudoers_tmp"
  if command -v visudo >/dev/null 2>&1; then
    visudo -cf "$sudoers_tmp"
  fi
  mv "$sudoers_tmp" "$sudoers_file"
}

save_previous_backend_requirements() {
  local requirements="$INSTALL_DIR/backend/requirements.txt"
  if [[ -f "$requirements" ]]; then
    cp -a "$requirements" "$PREVIOUS_REQUIREMENTS_FILE"
  fi
}

backend_requirements_unchanged() {
  local requirements="$INSTALL_DIR/backend/requirements.txt"
  [[ "${SKYWEAVER_FORCE_PIP_INSTALL:-0}" != "1" ]] || return 1
  [[ -x "$INSTALL_DIR/backend/.venv/bin/pip" ]] || return 1
  [[ -f "$PREVIOUS_REQUIREMENTS_FILE" && -f "$requirements" ]] || return 1
  cmp -s "$PREVIOUS_REQUIREMENTS_FILE" "$requirements"
}

install_backend_dependencies() {
  if backend_requirements_unchanged; then
    echo "Backend requirements unchanged; skipping pip install."
    return
  fi
  python3 -m venv "$INSTALL_DIR/backend/.venv"
  "$INSTALL_DIR/backend/.venv/bin/pip" install --upgrade pip
  "$INSTALL_DIR/backend/.venv/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt"
}

if [[ "${EUID}" -ne 0 ]]; then echo "Please run with sudo"; exit 1; fi
mkdir -p "$BACKUP_DIR"
systemctl stop skyweaver.target || true
cp -a /etc/skyweaver "$BACKUP_DIR/config" 2>/dev/null || true
cp -a /var/lib/skyweaver/skyweaver.db "$BACKUP_DIR/skyweaver.db" 2>/dev/null || true
save_previous_backend_requirements
grant_hardware_groups
install_zwo_sdk
install_service_controls
rsync -a --delete --exclude .git --exclude node_modules --exclude data --exclude logs "$ROOT_DIR/" "$INSTALL_DIR/"
install_backend_dependencies
npm ci --prefix "$INSTALL_DIR"
npm run build --prefix "$INSTALL_DIR"
rsync -a --delete "$INSTALL_DIR/dist/" /var/lib/skyweaver/web/
cp "$INSTALL_DIR/scripts/systemd/"*.service "$INSTALL_DIR/scripts/systemd/skyweaver.target" /etc/systemd/system/
systemctl daemon-reload
systemctl restart skyweaver.target
echo "Upgrade complete. Backup: $BACKUP_DIR"
