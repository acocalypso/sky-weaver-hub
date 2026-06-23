#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
FAKE_BIN="$TMP_DIR/fake-bin"
COMMAND_LOG="$TMP_DIR/commands.log"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

mkdir -p "$FAKE_BIN"
: >"$COMMAND_LOG"

write_fake() {
  local name="$1"
  shift
  cat >"$FAKE_BIN/$name"
  chmod +x "$FAKE_BIN/$name"
}

write_fake apt-get <<'EOF'
#!/usr/bin/env bash
echo "apt-get $*" >>"$SKYWEAVER_TEST_COMMAND_LOG"
EOF

write_fake apt-cache <<'EOF'
#!/usr/bin/env bash
echo "apt-cache $*" >>"$SKYWEAVER_TEST_COMMAND_LOG"
exit 1
EOF

write_fake chown <<'EOF'
#!/usr/bin/env bash
echo "chown $*" >>"$SKYWEAVER_TEST_COMMAND_LOG"
EOF

write_fake getent <<'EOF'
#!/usr/bin/env bash
echo "getent $*" >>"$SKYWEAVER_TEST_COMMAND_LOG"
case "$2" in
  video|render|input|gpio|i2c|spi) exit 0 ;;
esac
exit 2
EOF

write_fake usermod <<'EOF'
#!/usr/bin/env bash
echo "usermod $*" >>"$SKYWEAVER_TEST_COMMAND_LOG"
EOF

write_fake systemctl <<'EOF'
#!/usr/bin/env bash
echo "systemctl $*" >>"$SKYWEAVER_TEST_COMMAND_LOG"
EOF

write_fake openssl <<'EOF'
#!/usr/bin/env bash
if [[ "$1" == "rand" && "$2" == "-hex" ]]; then
  printf '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n'
  exit 0
fi
exit 1
EOF

write_fake python3 <<'EOF'
#!/usr/bin/env bash
echo "python3 $*" >>"$SKYWEAVER_TEST_COMMAND_LOG"
if [[ "$1" == "-m" && "$2" == "venv" ]]; then
  mkdir -p "$3/bin"
  cat >"$3/bin/pip" <<'PIP'
#!/usr/bin/env bash
echo "pip $*" >>"$SKYWEAVER_TEST_COMMAND_LOG"
PIP
  chmod +x "$3/bin/pip"
  cat >"$3/bin/python" <<'PYTHON'
#!/usr/bin/env bash
echo "python $*" >>"$SKYWEAVER_TEST_COMMAND_LOG"
printf '$2b$12$0123456789abcdefghijklmnopqrstuv0123456789abcdefghij\n'
PYTHON
  chmod +x "$3/bin/python"
fi
EOF

write_fake npm <<'EOF'
#!/usr/bin/env bash
echo "npm $*" >>"$SKYWEAVER_TEST_COMMAND_LOG"
prefix=""
for ((i = 1; i <= $#; i++)); do
  if [[ "${!i}" == "--prefix" ]]; then
    next=$((i + 1))
    prefix="${!next}"
  fi
done
if [[ "$1" == "run" && "$2" == "build" && -n "$prefix" ]]; then
  mkdir -p "$prefix/dist"
  printf 'built\n' >"$prefix/dist/index.html"
fi
EOF

write_fake rsync <<'EOF'
#!/usr/bin/env bash
echo "rsync $*" >>"$SKYWEAVER_TEST_COMMAND_LOG"
args=("$@")
src="${args[$((${#args[@]} - 2))]}"
dest="${args[$((${#args[@]} - 1))]}"
mkdir -p "$dest"
case "$dest" in
  */install/)
    mkdir -p "$dest/backend" "$dest/scripts/systemd"
    printf '{}\n' >"$dest/package.json"
    printf '# test requirements\n' >"$dest/backend/requirements.txt"
    if [[ -d "$src/scripts/systemd" ]]; then
      cp "$src/scripts/systemd/"* "$dest/scripts/systemd/"
    fi
    ;;
  */web/)
    if [[ -d "$src" ]]; then
      cp -R "$src"/. "$dest"/
    fi
    ;;
esac
EOF

assert_contains() {
  local needle="$1"
  local haystack="$2"
  if ! grep -Fq "$needle" "$haystack"; then
    echo "Expected '$needle' in $haystack"
    echo "--- $haystack ---"
    cat "$haystack"
    exit 1
  fi
}

run_installer() {
  local dry_run="$1"
  PATH="$FAKE_BIN:$PATH" \
    SKYWEAVER_TEST_COMMAND_LOG="$COMMAND_LOG" \
    SKYWEAVER_DRY_RUN="$dry_run" \
    SKYWEAVER_ALLOW_NON_ROOT=1 \
    SKYWEAVER_INSTALL_DIR="$TMP_DIR/install" \
    SKYWEAVER_CONFIG_DIR="$TMP_DIR/config" \
    SKYWEAVER_DATA_DIR="$TMP_DIR/data" \
    SKYWEAVER_LOG_DIR="$TMP_DIR/logs" \
    SKYWEAVER_SYSTEMD_DIR="$TMP_DIR/systemd" \
    SKYWEAVER_SERVICE_USER="$(id -un)" \
    SKYWEAVER_SERVICE_GROUP="$(id -gn)" \
    SKYWEAVER_CONFIG_OWNER="$(id -un)" \
    bash "$ROOT_DIR/install.sh"
}

dry_output="$TMP_DIR/dry-run.out"
run_installer 1 >"$dry_output"
assert_contains "+ apt-get update" "$dry_output"
assert_contains "+ install -m 640 skyweaver.env" "$dry_output"
if [[ -e "$TMP_DIR/config/skyweaver.env" ]]; then
  echo "Dry-run created a config file"
  exit 1
fi

run_installer 0 >"$TMP_DIR/install-1.out"
cp "$TMP_DIR/config/skyweaver.env" "$TMP_DIR/skyweaver.env.first"
run_installer 0 >"$TMP_DIR/install-2.out"
cmp "$TMP_DIR/skyweaver.env.first" "$TMP_DIR/config/skyweaver.env"

assert_contains "Keeping existing $TMP_DIR/config/skyweaver.env" "$TMP_DIR/install-2.out"
assert_contains "systemctl restart skyweaver.target" "$COMMAND_LOG"
assert_contains "usermod -a -G video" "$COMMAND_LOG"
assert_contains "usermod -a -G render" "$COMMAND_LOG"
[[ -f "$TMP_DIR/data/web/index.html" ]]
assert_contains "SKYWEAVER_ADMIN_PASSWORD_HASH='\$2b\$12\$0123456789abcdefghijklmnopqrstuv0123456789abcdefghij'" "$TMP_DIR/config/skyweaver.env"
assert_contains "SKYWEAVER_OBSERVATORY_TIMEZONE='" "$TMP_DIR/config/skyweaver.env"
assert_contains "SKYWEAVER_PRIMARY_CAMERA_ADAPTER='mock'" "$TMP_DIR/config/skyweaver.env"
[[ -f "$TMP_DIR/systemd/skyweaver-api.service" ]]
assert_contains "Environment=PYTHONPATH=/opt/skyweaver/backend" "$TMP_DIR/systemd/skyweaver-api.service"
assert_contains "Environment=PYTHONPATH=/opt/skyweaver/backend" "$TMP_DIR/systemd/skyweaver-capture.service"
assert_contains "Environment=PYTHONPATH=/opt/skyweaver/backend" "$TMP_DIR/systemd/skyweaver-worker.service"
assert_contains "SupplementaryGroups=video render input gpio i2c spi" "$TMP_DIR/systemd/skyweaver-api.service"
assert_contains "SupplementaryGroups=video render input gpio i2c spi" "$TMP_DIR/systemd/skyweaver-capture.service"
assert_contains "SupplementaryGroups=video render input gpio i2c spi" "$TMP_DIR/systemd/skyweaver-worker.service"

echo "install.sh dry-run and idempotency checks passed"
