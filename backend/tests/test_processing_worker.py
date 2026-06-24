import asyncio
import shutil
from pathlib import Path

from test_api import login, make_client, run_queued_test_capture


def test_worker_generates_keogram_product(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    day_key = None
    for _ in range(3):
        _queued, _job, image = run_queued_test_capture(client, headers, {"exposure_ms": 250, "gain": 1, "format": "jpg", "mode": "night"})
        day_key = image["captured_at"][:10].replace("-", "")

    queued = client.post("/api/v1/products/keogram", headers=headers, json={"day_key": day_key}).json()["data"]
    assert queued["status"] == "pending"
    pending_jobs = client.get("/api/v1/processing/jobs", headers=headers).json()["data"]
    assert pending_jobs[0]["id"] == queued["id"]
    assert pending_jobs[0]["status"] == "pending"

    from skyweaver.services.processing import run_once

    assert asyncio.run(run_once()) is True
    completed_job = client.get(f"/api/v1/processing/jobs/{queued['id']}", headers=headers).json()["data"]
    assert completed_job["status"] == "completed"
    assert completed_job["progress"] == 1

    products = client.get("/api/v1/products", headers=headers).json()["data"]
    assert len(products) == 1
    product = products[0]
    assert product["id"] == queued["id"]
    assert product["type"] == "keogram"
    assert product["status"] == "completed"
    assert product["metadata"]["source_images"] == 3
    assert Path(product["file_path"]).exists()

    download = client.get(f"/api/v1/products/{product['id']}/download")
    assert download.status_code == 200


def test_worker_generates_timelapse_product(tmp_path: Path):
    if not shutil.which("ffmpeg"):
        import pytest

        pytest.skip("ffmpeg is required for timelapse generation")

    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    day_key = None
    for _ in range(3):
        _queued, _job, image = run_queued_test_capture(client, headers, {"exposure_ms": 250, "gain": 1, "format": "jpg", "mode": "night"})
        day_key = image["captured_at"][:10].replace("-", "")

    queued = client.post("/api/v1/products/timelapse", headers=headers, json={"day_key": day_key, "fps": 10, "codec": "h264"}).json()["data"]
    assert queued["status"] == "pending"
    assert queued["type"] == "timelapse"
    assert queued["input"]["day_key"] == day_key

    from skyweaver.services.processing import run_once

    assert asyncio.run(run_once()) is True
    completed_job = client.get(f"/api/v1/processing/jobs/{queued['id']}", headers=headers).json()["data"]
    assert completed_job["status"] == "completed"
    assert completed_job["progress"] == 1

    products = client.get("/api/v1/products", headers=headers).json()["data"]
    product = next(item for item in products if item["id"] == queued["id"])
    assert product["type"] == "timelapse"
    assert product["status"] == "completed"
    assert product["metadata"]["source_images"] == 3
    assert product["metadata"]["fps"] == 10
    assert Path(product["file_path"]).exists()
    assert Path(product["file_path"]).suffix == ".mp4"

    download = client.get(f"/api/v1/products/{product['id']}/download")
    assert download.status_code == 200


def test_worker_generates_mini_timelapse_product(tmp_path: Path):
    if not shutil.which("ffmpeg"):
        import pytest

        pytest.skip("ffmpeg is required for mini timelapse generation")

    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    day_key = None
    for _ in range(5):
        _queued, _job, image = run_queued_test_capture(client, headers, {"exposure_ms": 250, "gain": 1, "format": "jpg", "mode": "night"})
        day_key = image["captured_at"][:10].replace("-", "")

    queued = client.post(
        "/api/v1/products/mini-timelapse",
        headers=headers,
        json={"day_key": day_key, "fps": 8, "codec": "h264", "max_frames": 3, "max_width": 640},
    ).json()["data"]
    assert queued["status"] == "pending"
    assert queued["type"] == "mini_timelapse"
    assert queued["input"]["day_key"] == day_key

    from skyweaver.services.processing import run_once

    assert asyncio.run(run_once()) is True
    completed_job = client.get(f"/api/v1/processing/jobs/{queued['id']}", headers=headers).json()["data"]
    assert completed_job["status"] == "completed"
    assert completed_job["progress"] == 1

    products = client.get("/api/v1/products", headers=headers).json()["data"]
    product = next(item for item in products if item["id"] == queued["id"])
    assert product["type"] == "mini_timelapse"
    assert product["status"] == "completed"
    assert product["metadata"]["source_images"] == 5
    assert product["metadata"]["used_images"] == 3
    assert product["metadata"]["mini"] is True
    assert Path(product["file_path"]).exists()
    assert Path(product["file_path"]).suffix == ".mp4"

    download = client.get(f"/api/v1/products/{product['id']}/download")
    assert download.status_code == 200


def test_worker_generates_startrail_product(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    day_key = None
    for _ in range(3):
        _queued, _job, image = run_queued_test_capture(client, headers, {"exposure_ms": 250, "gain": 1, "format": "jpg", "mode": "night"})
        day_key = image["captured_at"][:10].replace("-", "")

    queued = client.post("/api/v1/products/startrail", headers=headers, json={"day_key": day_key, "max_width": 1280}).json()["data"]
    assert queued["status"] == "pending"
    assert queued["type"] == "startrail"
    assert queued["input"]["day_key"] == day_key

    from skyweaver.services.processing import run_once

    assert asyncio.run(run_once()) is True
    completed_job = client.get(f"/api/v1/processing/jobs/{queued['id']}", headers=headers).json()["data"]
    assert completed_job["status"] == "completed"
    assert completed_job["progress"] == 1

    products = client.get("/api/v1/products", headers=headers).json()["data"]
    product = next(item for item in products if item["id"] == queued["id"])
    assert product["type"] == "startrail"
    assert product["status"] == "completed"
    assert product["metadata"]["source_images"] == 3
    assert product["metadata"]["kind"] == "lighten-blend"
    assert Path(product["file_path"]).exists()
    assert Path(product["file_path"]).suffix == ".jpg"

    download = client.get(f"/api/v1/products/{product['id']}/download")
    assert download.status_code == 200
