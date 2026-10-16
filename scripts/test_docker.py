"""Exercise the real Compose stack using only Python's standard library.

Run against disposable volumes, never an existing observatory deployment.
"""

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-persistence", action="store_true")
    args = parser.parse_args()
    base = os.environ.get("SKYWEAVER_TEST_URL", "http://127.0.0.1:8765").rstrip("/")
    token = None

    def request(path, payload=None, *, raw=False):
        headers = {"Accept": "text/html" if raw else "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(base + path, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            body = response.read()
            return body if raw else json.loads(body)["data"]

    def wait_for_job(path):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            job = request(path)
            if job["status"] == "completed":
                return job
            if job["status"] in {"failed", "canceled", "cancelled"}:
                raise RuntimeError(f"Job failed: {job}")
            time.sleep(0.5)
        raise TimeoutError(f"Job did not complete: {path}")

    assert request("/api/v1/health")["status"] == "ok"
    for path in ("/", "/public", "/dashboard"):
        assert b'id="root"' in request(path, raw=True), path
    credentials = {
        "username": os.environ.get("SKYWEAVER_ADMIN_USERNAME", "admin"),
        "password": os.environ["SKYWEAVER_ADMIN_PASSWORD"],
    }
    token = request("/api/v1/auth/login", credentials)["token"]
    services = request("/api/v1/system/services")
    assert all(row["managed_by"] == "docker" and row["actions"] == [] for row in services)

    state_path = Path(".tmp/docker-smoke.json")
    if args.check_persistence:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        image = request(f"/api/v1/images/{state['image_id']}")
        assert image["id"] == state["image_id"]
        assert request(f"/api/v1/images/{image['id']}/download", raw=True)
        for product_id in state["product_ids"]:
            assert request(f"/api/v1/products/{product_id}")["status"] == "completed"
            assert request(f"/api/v1/products/{product_id}/download", raw=True)
        capture = request("/api/v1/capture/test-shot", {
            "exposure_ms": 10, "gain": 1, "format": "jpg", "mode": "manual",
        })
        wait_for_job(f"/api/v1/capture/jobs/{capture['id']}")
        job = request("/api/v1/products/keogram", {
            "day_key": image["day_key"], "skip_bad_images": False,
        })
        wait_for_job(f"/api/v1/processing/jobs/{job['id']}")
        print("Recreation preserved data and UI; capture/processing resumed after abrupt shutdown.")
        return

    # These jobs must be consumed by the real daemon and worker containers.
    capture = request("/api/v1/capture/test-shot", {
        "exposure_ms": 10, "gain": 1, "format": "jpg", "mode": "manual",
    })
    capture = wait_for_job(f"/api/v1/capture/jobs/{capture['id']}")
    image_id = capture["result"]["image_id"]
    image = request(f"/api/v1/images/{image_id}")
    assert request(f"/api/v1/images/{image_id}/download", raw=True)
    product_ids = []
    for product_type in ("keogram", "timelapse"):
        job = request(f"/api/v1/products/{product_type}", {
            "day_key": image["day_key"], "skip_bad_images": False, "max_width": 640,
        })
        result = wait_for_job(f"/api/v1/processing/jobs/{job['id']}")
        product_id = result["output"]["product_id"]
        assert request(f"/api/v1/products/{product_id}/download", raw=True)
        product_ids.append(product_id)
    state_path.parent.mkdir(exist_ok=True)
    state_path.write_text(json.dumps({"image_id": image_id, "product_ids": product_ids}), encoding="utf-8")
    print("Compose smoke passed: login, web UI, mock capture, keogram and ffmpeg timelapse.")


if __name__ == "__main__":
    main()
