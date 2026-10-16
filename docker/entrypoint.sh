#!/bin/sh
set -eu

: "${SKYWEAVER_SECRET_KEY:?Set SKYWEAVER_SECRET_KEY to a persistent random secret}"
if [ "${#SKYWEAVER_SECRET_KEY}" -lt 32 ]; then
    echo 'SKYWEAVER_SECRET_KEY must contain at least 32 characters.' >&2
    exit 1
fi
if [ -z "${SKYWEAVER_ADMIN_PASSWORD:-}${SKYWEAVER_ADMIN_PASSWORD_HASH:-}" ]; then
    echo 'Set SKYWEAVER_ADMIN_PASSWORD or SKYWEAVER_ADMIN_PASSWORD_HASH for bootstrap.' >&2
    exit 1
fi

if [ "$#" -eq 0 ]; then set -- api; fi
case "$1" in
    api) shift; set -- python -m uvicorn skyweaver.main:app --host 0.0.0.0 --port 8765 "$@" ;;
    capture)
        shift
        # Container PIDs can repeat after recreation. A kernel lock guards the
        # singleton before discarding the previous container's stale PID file.
        set -- flock --nonblock --no-fork "$SKYWEAVER_DATA_DIR/.container-capture.lock" \
            sh -c 'rm -f "$SKYWEAVER_DATA_DIR/capture-daemon.lock"; exec python -m skyweaver.capture_daemon "$@"' capture "$@"
        ;;
    worker)
        shift
        set -- flock --nonblock --no-fork "$SKYWEAVER_DATA_DIR/.container-worker.lock" \
            python -m skyweaver.worker "$@"
        ;;
esac

# Serialize initial schema creation/seeding across independently started roles.
# The lock is released before starting the long-running process.
mkdir -p "$SKYWEAVER_DATA_DIR" "$SKYWEAVER_CONFIG_DIR" "$SKYWEAVER_LOG_DIR"
flock "$SKYWEAVER_DATA_DIR/.container-init.lock" \
    python -c 'from skyweaver.db import init_db; init_db()'
exec "$@"
