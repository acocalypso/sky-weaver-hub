import asyncio
import shutil
from pathlib import Path

from PIL import Image

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


def test_worker_uploads_latest_image_to_rsync_ssh_target(tmp_path: Path, monkeypatch):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    _queued, _job, image = run_queued_test_capture(client, headers, {"exposure_ms": 250, "gain": 1, "format": "jpg", "mode": "night"})
    commands: list[list[str]] = []

    from skyweaver.services import uploads

    monkeypatch.setattr(uploads.shutil, "which", lambda name: f"/usr/bin/{name}" if name in {"rsync", "ssh"} else None)

    def fake_run(command, **kwargs):
        commands.append(command)

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return Result()

    monkeypatch.setattr(uploads.subprocess, "run", fake_run)

    target_res = client.post(
        "/api/v1/remote-targets",
        headers=headers,
        json={
            "name": "Website rsync",
            "type": "rsync_ssh",
            "enabled": True,
            "config": {"host": "allsky.example", "username": "skyweaver", "remote_path": "/srv/allsky", "port": 2222, "ssh_key_path": "/home/skyweaver/.ssh/id_ed25519"},
        },
    )
    assert target_res.status_code == 200, target_res.text
    target = target_res.json()["data"]
    assert target["config"]["ssh_key_path"] == "/home/skyweaver/.ssh/id_ed25519"

    test_res = client.post(f"/api/v1/remote-targets/{target['id']}/test", headers=headers)
    assert test_res.status_code == 200, test_res.text
    assert test_res.json()["data"]["status"] == "configured"

    queue_res = client.post("/api/v1/uploads/queue", headers=headers, json={"source_type": "latest", "target_id": target["id"]})
    assert queue_res.status_code == 200, queue_res.text
    queued_upload = queue_res.json()["data"]

    from skyweaver.services.processing import run_once

    assert asyncio.run(run_once()) is True
    assert commands
    command = commands[0]
    assert command[:4] == ["rsync", "-az", "--mkpath", "-e"]
    assert str(Path(image["file_path"])) in command
    assert command[-1].endswith(f"/image/{image['id']}/{Path(image['file_path']).name}")

    upload_jobs = client.get("/api/v1/uploads/jobs", headers=headers).json()["data"]
    upload = next(item for item in upload_jobs if item["id"] == queued_upload["upload_job_ids"][0])
    assert upload["status"] == "completed"
    assert upload["destination_path"].startswith("rsync://skyweaver@allsky.example:/srv/allsky/")


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


def test_worker_imports_and_rolls_back_allsky_files(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    allsky = tmp_path / "allsky"
    image_source = allsky / "images" / "2026-06-30" / "capture_20260630_010203.jpg"
    keogram_source = allsky / "images" / "2026-06-30" / "keogram_20260630.jpg"
    timelapse_source = allsky / "videos" / "timelapse_20260630.mp4"
    config_source = allsky / "config.sh"
    image_source.parent.mkdir(parents=True)
    timelapse_source.parent.mkdir(parents=True)
    Image.new("RGB", (64, 48), "navy").save(image_source)
    Image.new("RGB", (64, 12), "white").save(keogram_source)
    timelapse_source.write_bytes(b"fake-mp4")
    config_source.write_text(
        "\n".join([
            "LATITUDE=49.1",
            "LONGITUDE=10.12",
            "LOCATION='Garden Allsky'",
            "TIMEZONE=Europe/Berlin",
            "ANGLE=-12",
            "CAMERA_TYPE=IMX290",
            "USEWEBSITE=true",
            "UNSUPPORTED_FOO=bar",
        ]),
        encoding="utf-8",
    )

    preview = client.post("/api/v1/migration/allsky/preview", headers=headers, json={"path": str(allsky)})
    assert preview.status_code == 200, preview.text
    preview_data = preview.json()["data"]
    assert preview_data["counts"] == {"images": 1, "timelapses": 1, "keograms": 1, "startrails": 0}
    assert preview_data["unsupported_settings"][0]["path"] == str(config_source)
    assert preview_data["settings"]["observatory"]["name"] == "Garden Allsky"
    assert preview_data["settings"]["observatory"]["latitude"] == 49.1
    assert preview_data["settings"]["schedule"]["sun_angle"] == -12
    assert any(item.get("key") == "UNSUPPORTED_FOO" for item in preview_data["unsupported_settings"])
    assert preview_data["will_delete_original"] is False

    queued = client.post("/api/v1/migration/allsky/import", headers=headers, json={"path": str(allsky)})
    assert queued.status_code == 200, queued.text
    job_id = queued.json()["data"]["id"]

    from skyweaver.services.processing import run_once

    assert asyncio.run(run_once()) is True
    completed = client.get(f"/api/v1/migration/jobs/{job_id}", headers=headers).json()["data"]
    assert completed["status"] == "completed"
    assert completed["output"]["imported_images"] == 1
    assert completed["output"]["imported_products"] == 2
    assert completed["output"]["settings"]["applied"]["camera_hints"]["hint"] == "IMX290"
    assert image_source.exists()
    assert keogram_source.exists()
    assert timelapse_source.exists()

    images = client.get("/api/v1/images", headers=headers).json()["data"]
    imported_image = next(item for item in images if item["metadata"]["migration"]["job_id"] == job_id)
    assert Path(imported_image["file_path"]).exists()
    assert imported_image["metadata"]["migration"]["original_path"] == str(image_source)
    products = client.get("/api/v1/products", headers=headers).json()["data"]
    imported_products = [item for item in products if item["metadata"]["migration"]["job_id"] == job_id]
    assert {item["type"] for item in imported_products} == {"keogram", "timelapse"}
    copied_paths = [Path(imported_image["file_path"]), *(Path(item["file_path"]) for item in imported_products)]
    assert all(path.exists() for path in copied_paths)
    settings_after_import = client.get("/api/v1/settings", headers=headers).json()["data"]
    assert settings_after_import["observatory"]["name"] == "Garden Allsky"
    assert settings_after_import["observatory"]["latitude"] == 49.1
    assert settings_after_import["observatory"]["longitude"] == 10.12
    assert settings_after_import["allsky_camera_hints"]["hint"] == "IMX290"
    schedule_after_import = client.get("/api/v1/schedule", headers=headers).json()["data"]
    assert schedule_after_import["sun_angle"] == -12

    rollback = client.post(f"/api/v1/migration/jobs/{job_id}/rollback", headers=headers)
    assert rollback.status_code == 200, rollback.text
    rollback_data = rollback.json()["data"]
    assert rollback_data["deleted_images"] == 1
    assert rollback_data["deleted_products"] == 2
    assert rollback_data["settings_restored"]["restored"] is True
    assert all(not path.exists() for path in copied_paths)
    assert image_source.exists()
    assert keogram_source.exists()
    assert timelapse_source.exists()
    settings_after_rollback = client.get("/api/v1/settings", headers=headers).json()["data"]
    assert settings_after_rollback["observatory"]["name"] == "Sky Weaver Observatory"
    assert "allsky_camera_hints" not in settings_after_rollback
    schedule_after_rollback = client.get("/api/v1/schedule", headers=headers).json()["data"]
    assert schedule_after_rollback["sun_angle"] == -6
