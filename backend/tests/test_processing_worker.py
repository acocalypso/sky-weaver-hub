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


def test_delete_product_removes_files_and_row(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    day_key = None
    for _ in range(3):
        _queued, _job, image = run_queued_test_capture(client, headers, {"exposure_ms": 250, "gain": 1, "format": "jpg", "mode": "night"})
        day_key = image["captured_at"][:10].replace("-", "")

    queued = client.post("/api/v1/products/keogram", headers=headers, json={"day_key": day_key}).json()["data"]

    from skyweaver.services.processing import run_once

    assert asyncio.run(run_once()) is True
    product = client.get(f"/api/v1/products/{queued['id']}", headers=headers).json()["data"]
    file_path = Path(product["file_path"])
    thumbnail_path = Path(product["thumbnail_path"])
    assert file_path.exists()
    assert thumbnail_path.exists()

    delete_res = client.delete(f"/api/v1/products/{product['id']}", headers=headers)
    assert delete_res.status_code == 200, delete_res.text
    payload = delete_res.json()["data"]
    assert payload["deleted"] == product["id"]
    assert str(file_path) in payload["deleted_files"]
    assert str(thumbnail_path) in payload["deleted_files"]
    assert not file_path.exists()
    assert not thumbnail_path.exists()
    assert client.get(f"/api/v1/products/{product['id']}", headers=headers).status_code == 404
    assert client.get(f"/api/v1/products/{product['id']}/download").status_code == 404


def test_product_retention_cleanup_removes_old_products_only(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    from skyweaver.db import json_dumps, new_id, now_iso, session
    from skyweaver.config import get_settings

    settings = get_settings()
    old_id = new_id()
    new_id_value = new_id()
    old_file = settings.product_dir / "20200101" / "old-keogram.jpg"
    old_thumb = settings.thumbnail_dir / "20200101" / "old-keogram.jpg"
    new_file = settings.product_dir / "20260629" / "new-keogram.jpg"
    for path in (old_file, old_thumb, new_file):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"product")

    with session() as conn:
        conn.execute(
            "INSERT INTO night_products (id, type, day_key, file_path, thumbnail_path, status, metadata, created_at) VALUES (?, 'keogram', '20200101', ?, ?, 'completed', ?, ?)",
            (old_id, str(old_file), str(old_thumb), json_dumps({"source_images": 3}), "2020-01-01T00:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO night_products (id, type, day_key, file_path, thumbnail_path, status, metadata, created_at) VALUES (?, 'keogram', '20260629', ?, NULL, 'completed', ?, ?)",
            (new_id_value, str(new_file), json_dumps({"source_images": 3}), now_iso()),
        )

    cleanup_res = client.post("/api/v1/products/retention/run?days=30", headers=headers)
    assert cleanup_res.status_code == 200, cleanup_res.text
    payload = cleanup_res.json()["data"]
    assert payload["retention_days"] == 30
    assert payload["deleted_products"] == 1
    assert payload["deleted_product_ids"] == [old_id]
    assert str(old_file) in payload["deleted_files"]
    assert str(old_thumb) in payload["deleted_files"]
    assert not old_file.exists()
    assert not old_thumb.exists()
    assert new_file.exists()
    assert client.get(f"/api/v1/products/{new_id_value}", headers=headers).status_code == 200


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


def test_worker_uploads_latest_image_to_filesystem_target(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    _queued, _job, image = run_queued_test_capture(client, headers, {"exposure_ms": 250, "gain": 1, "format": "jpg", "mode": "night"})
    destination = tmp_path / "remote-target"

    target_res = client.post(
        "/api/v1/remote-targets",
        headers=headers,
        json={"name": "Local mirror", "type": "filesystem", "enabled": True, "config": {"destination_path": str(destination)}},
    )
    assert target_res.status_code == 200, target_res.text
    target = target_res.json()["data"]
    assert target["config"]["destination_path"] == str(destination)

    test_res = client.post(f"/api/v1/remote-targets/{target['id']}/test", headers=headers)
    assert test_res.status_code == 200, test_res.text
    assert test_res.json()["data"]["status"] == "ready"

    queue_res = client.post("/api/v1/uploads/queue", headers=headers, json={"source_type": "latest"})
    assert queue_res.status_code == 200, queue_res.text
    queued_upload = queue_res.json()["data"]
    assert queued_upload["status"] == "pending"
    assert len(queued_upload["upload_job_ids"]) == 1

    from skyweaver.services.processing import run_once

    assert asyncio.run(run_once()) is True
    upload_jobs = client.get("/api/v1/uploads/jobs", headers=headers).json()["data"]
    upload = next(item for item in upload_jobs if item["id"] == queued_upload["upload_job_ids"][0])
    assert upload["status"] == "completed"
    assert upload["attempts"] == 1
    copied = Path(upload["destination_path"])
    assert copied.exists()
    assert copied.read_bytes() == Path(image["file_path"]).read_bytes()
    assert copied.parent == destination / "image" / image["id"]


def test_upload_retry_requeues_failed_uploads(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    missing_source = tmp_path / "missing.jpg"
    target_destination = tmp_path / "remote-target"

    from skyweaver.db import json_dumps, new_id, now_iso, session

    target_id = new_id()
    upload_id = new_id()
    with session() as conn:
        conn.execute(
            "INSERT INTO remote_targets (id, name, type, config_encrypted, enabled, created_at, updated_at) VALUES (?, 'Local mirror', 'filesystem', ?, 1, ?, ?)",
            (target_id, json_dumps({"destination_path": str(target_destination)}), now_iso(), now_iso()),
        )
        conn.execute(
            "INSERT INTO upload_jobs (id, target_id, source_type, source_id, source_path, status, attempts, last_error, created_at) VALUES (?, ?, 'image', 'missing-image', ?, 'failed', 1, 'missing', ?)",
            (upload_id, target_id, str(missing_source), now_iso()),
        )

    retry_res = client.post("/api/v1/uploads/retry", headers=headers)
    assert retry_res.status_code == 200, retry_res.text
    payload = retry_res.json()["data"]
    assert payload["status"] == "pending"
    assert payload["upload_job_ids"] == [upload_id]

    jobs = client.get("/api/v1/uploads/jobs", headers=headers).json()["data"]
    retried = next(item for item in jobs if item["id"] == upload_id)
    assert retried["status"] == "pending"
    assert retried["last_error"] is None
