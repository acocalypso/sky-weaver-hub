"""Check API readiness or ownership of a role's kernel singleton lock."""

import fcntl
import os
import sys
import urllib.request
from pathlib import Path


def main() -> int:
    role = sys.argv[1]
    if role == "api":
        with urllib.request.urlopen("http://127.0.0.1:8765/api/v1/health", timeout=3) as response:
            return 0 if response.status == 200 else 1
    lock_names = {"capture": ".container-capture.lock", "worker": ".container-worker.lock"}
    lock_path = Path(os.environ["SKYWEAVER_DATA_DIR"]) / lock_names[role]
    # A live role holds this lock throughout execution, including long captures
    # and video jobs that legitimately delay database heartbeat updates.
    try:
        lock_file = lock_path.open("rb")
    except FileNotFoundError:
        return 1
    with lock_file as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        return 1


if __name__ == "__main__":
    sys.exit(main())
