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
    assert upload["target_name"] == "Local mirror"
    assert upload["target_type"] == "filesystem"
    detail = client.get(f"/api/v1/uploads/jobs/{upload['id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["target_name"] == "Local mirror"
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


def test_worker_uploads_latest_image_to_scp_ssh_target(tmp_path: Path, monkeypatch):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    _queued, _job, image = run_queued_test_capture(client, headers, {"exposure_ms": 250, "gain": 1, "format": "jpg", "mode": "night"})
    commands: list[list[str]] = []

    from skyweaver.services import uploads

    monkeypatch.setattr(uploads.shutil, "which", lambda name: f"/usr/bin/{name}" if name in {"scp", "ssh"} else None)

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
            "name": "Website scp",
            "type": "scp_ssh",
            "enabled": True,
            "config": {"host": "allsky.example", "username": "skyweaver", "remote_path": "/srv/allsky", "port": 2222, "ssh_key_path": "/home/skyweaver/.ssh/id_ed25519"},
        },
    )
    assert target_res.status_code == 200, target_res.text
    target = target_res.json()["data"]

    test_res = client.post(f"/api/v1/remote-targets/{target['id']}/test", headers=headers)
    assert test_res.status_code == 200, test_res.text
    assert test_res.json()["data"]["destination_path"].startswith("scp://skyweaver@allsky.example:/srv/allsky")

    queue_res = client.post("/api/v1/uploads/queue", headers=headers, json={"source_type": "latest", "target_id": target["id"]})
    assert queue_res.status_code == 200, queue_res.text
    queued_upload = queue_res.json()["data"]

    from skyweaver.services.processing import run_once

    assert asyncio.run(run_once()) is True
    assert len(commands) == 2
    assert commands[0][:5] == ["ssh", "-p", "2222", "-o", "BatchMode=yes"]
    assert commands[0][-3:] == ["mkdir", "-p", f"/srv/allsky/image/{image['id']}"]
    assert commands[1][:5] == ["scp", "-P", "2222", "-o", "BatchMode=yes"]
    assert str(Path(image["file_path"])) in commands[1]
    assert commands[1][-1].endswith(f"/image/{image['id']}/{Path(image['file_path']).name}")

    upload_jobs = client.get("/api/v1/uploads/jobs", headers=headers).json()["data"]
    upload = next(item for item in upload_jobs if item["id"] == queued_upload["upload_job_ids"][0])
    assert upload["status"] == "completed"
    assert upload["target_type"] == "scp_ssh"
    assert upload["destination_path"].startswith("scp://skyweaver@allsky.example:/srv/allsky/")


def test_worker_uploads_latest_image_to_sftp_ssh_target(tmp_path: Path, monkeypatch):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    _queued, _job, image = run_queued_test_capture(client, headers, {"exposure_ms": 250, "gain": 1, "format": "jpg", "mode": "night"})
    commands: list[list[str]] = []

    from skyweaver.services import uploads

    monkeypatch.setattr(uploads.shutil, "which", lambda name: f"/usr/bin/{name}" if name in {"sftp", "ssh"} else None)

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[0] == "sftp":
            assert "input" in kwargs
            assert f"put {Path(image['file_path']).as_posix()} /srv/allsky/image/{image['id']}/{Path(image['file_path']).name}" in kwargs["input"]

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
            "name": "Website sftp",
            "type": "sftp_ssh",
            "enabled": True,
            "config": {"host": "allsky.example", "username": "skyweaver", "remote_path": "/srv/allsky", "port": 2222, "ssh_key_path": "/home/skyweaver/.ssh/id_ed25519"},
        },
    )
    assert target_res.status_code == 200, target_res.text
    target = target_res.json()["data"]

    test_res = client.post(f"/api/v1/remote-targets/{target['id']}/test", headers=headers)
    assert test_res.status_code == 200, test_res.text
    assert test_res.json()["data"]["destination_path"].startswith("sftp://skyweaver@allsky.example:/srv/allsky")

    queue_res = client.post("/api/v1/uploads/queue", headers=headers, json={"source_type": "latest", "target_id": target["id"]})
    assert queue_res.status_code == 200, queue_res.text
    queued_upload = queue_res.json()["data"]

    from skyweaver.services.processing import run_once

    assert asyncio.run(run_once()) is True
    assert len(commands) == 2
    assert commands[0][:5] == ["ssh", "-p", "2222", "-o", "BatchMode=yes"]
    assert commands[1][:5] == ["sftp", "-P", "2222", "-o", "BatchMode=yes"]

    upload_jobs = client.get("/api/v1/uploads/jobs", headers=headers).json()["data"]
    upload = next(item for item in upload_jobs if item["id"] == queued_upload["upload_job_ids"][0])
    assert upload["status"] == "completed"
    assert upload["target_type"] == "sftp_ssh"
    assert upload["destination_path"].startswith("sftp://skyweaver@allsky.example:/srv/allsky/")


def test_worker_uploads_latest_image_to_ftps_target(tmp_path: Path, monkeypatch):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    _queued, _job, image = run_queued_test_capture(client, headers, {"exposure_ms": 250, "gain": 1, "format": "jpg", "mode": "night"})
    operations: list[tuple[str, object]] = []

    from skyweaver.services import uploads

    class FakeFTPS:
        directories = {"/", "srv", "allsky", "image"}

        def __init__(self, **kwargs):
            operations.append(("init", kwargs))

        def connect(self, host, port, timeout=None):
            operations.append(("connect", (host, port, timeout)))

        def login(self, username, password):
            operations.append(("login", (username, password)))

        def prot_p(self):
            operations.append(("prot_p", True))

        def set_pasv(self, passive):
            operations.append(("passive", passive))

        def cwd(self, path):
            operations.append(("cwd", path))
            if path not in self.directories:
                raise OSError(path)

        def mkd(self, path):
            self.directories.add(path)
            operations.append(("mkd", path))

        def storbinary(self, command, handle):
            operations.append(("store", (command, handle.read())))

        def quit(self):
            operations.append(("quit", True))

        def close(self):
            operations.append(("close", True))

    monkeypatch.setattr(uploads, "FTP_TLS", FakeFTPS)

    target_res = client.post(
        "/api/v1/remote-targets",
        headers=headers,
        json={
            "name": "Website ftps",
            "type": "ftps",
            "enabled": True,
            "config": {"host": "ftp.example", "username": "skyweaver", "password": "secret", "remote_path": "/srv/allsky", "port": 21, "passive": True},
        },
    )
    assert target_res.status_code == 200, target_res.text
    target = target_res.json()["data"]
    assert target["config"]["password"] == "***"
    from skyweaver.db import json_loads, session
    from skyweaver.secrets import decrypt_config_envelope

    with session() as conn:
        stored = conn.execute("SELECT config_encrypted FROM remote_targets WHERE id=?", (target["id"],)).fetchone()["config_encrypted"]
    stored_config = json_loads(stored, {})
    assert stored_config["_skyweaver_secret"] == "fernet.v1"
    assert '"password":"secret"' not in stored
    assert decrypt_config_envelope(stored_config)["password"] == "secret"

    test_res = client.post(f"/api/v1/remote-targets/{target['id']}/test", headers=headers)
    assert test_res.status_code == 200, test_res.text

    queue_res = client.post("/api/v1/uploads/queue", headers=headers, json={"source_type": "latest", "target_id": target["id"]})
    assert queue_res.status_code == 200, queue_res.text
    queued_upload = queue_res.json()["data"]

    from skyweaver.services.processing import run_once

    assert asyncio.run(run_once()) is True
    assert ("login", ("skyweaver", "secret")) in operations
    assert ("prot_p", True) in operations
    assert any(item[0] == "store" and item[1][0] == f"STOR {Path(image['file_path']).name}" for item in operations)

    upload_jobs = client.get("/api/v1/uploads/jobs", headers=headers).json()["data"]
    upload = next(item for item in upload_jobs if item["id"] == queued_upload["upload_job_ids"][0])
    assert upload["status"] == "completed"
    assert upload["target_type"] == "ftps"
    assert upload["destination_path"].startswith("ftps://skyweaver@ftp.example:/srv/allsky/")


def test_copy_to_ftp_target_uses_plain_ftp_without_tls(tmp_path: Path, monkeypatch):
    source = tmp_path / "capture.jpg"
    source.write_bytes(b"capture")
    operations: list[tuple[str, object]] = []

    from skyweaver.services import uploads

    class FakeFTP:
        directories = {"/", "srv", "allsky", "image", "image-id"}

        def __init__(self, **kwargs):
            operations.append(("init", kwargs))

        def connect(self, host, port, timeout=None):
            operations.append(("connect", (host, port, timeout)))

        def login(self, username, password):
            operations.append(("login", (username, password)))

        def set_pasv(self, passive):
            operations.append(("passive", passive))

        def cwd(self, path):
            operations.append(("cwd", path))
            if path not in self.directories:
                raise OSError(path)

        def mkd(self, path):
            self.directories.add(path)
            operations.append(("mkd", path))

        def storbinary(self, command, handle):
            operations.append(("store", (command, handle.read())))

        def quit(self):
            operations.append(("quit", True))

        def close(self):
            operations.append(("close", True))

    monkeypatch.setattr(uploads, "FTP", FakeFTP)
    destination = uploads.copy_to_ftp_target(
        {"source_path": str(source), "source_type": "image", "source_id": "image-id"},
        {"type": "ftp", "config_encrypted": {"host": "ftp.example", "username": "skyweaver", "password": "secret", "remote_path": "/srv/allsky", "port": 21}},
    )

    assert destination == "ftp://skyweaver@ftp.example:/srv/allsky/image/image-id/capture.jpg"
    assert ("login", ("skyweaver", "secret")) in operations
    assert not any(item[0] == "prot_p" for item in operations)
    assert ("store", ("STOR capture.jpg", b"capture")) in operations


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


def test_dark_frame_delete_removes_skyweaver_files(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    frame_path = tmp_path / "data" / "dark-frames" / "20260630" / "dark.jpg"
    thumb_path = tmp_path / "data" / "thumbnails" / "dark-frames" / "20260630" / "dark.jpg"
    frame_path.parent.mkdir(parents=True)
    thumb_path.parent.mkdir(parents=True)
    Image.new("RGB", (32, 24), "black").save(frame_path)
    Image.new("RGB", (16, 12), "black").save(thumb_path)

    from skyweaver.db import json_dumps, new_id, now_iso, session

    frame_id = new_id()
    with session() as conn:
        conn.execute(
            """INSERT INTO dark_frames
               (id, camera_id, captured_at, day_key, file_path, thumbnail_path, format, width, height, size_bytes, metadata, created_at)
               VALUES (?, NULL, ?, '20260630', ?, ?, 'jpg', 32, 24, ?, ?, ?)""",
            (frame_id, now_iso(), str(frame_path), str(thumb_path), frame_path.stat().st_size, json_dumps({"test": True}), now_iso()),
        )

    listed = client.get("/api/v1/dark-frames", headers=headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"][0]["id"] == frame_id

    deleted = client.delete(f"/api/v1/dark-frames/{frame_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["deleted"] == frame_id
    assert not frame_path.exists()
    assert not thumb_path.exists()
    assert client.get("/api/v1/dark-frames", headers=headers).json()["data"] == []


def test_worker_imports_and_rolls_back_allsky_files(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    allsky = tmp_path / "allsky"
    image_source = allsky / "images" / "2026-06-30" / "capture_20260630_010203.jpg"
    html_asset = allsky / "html" / "documentation" / "logo.jpg"
    overlay_asset = allsky / "config" / "overlay" / "images" / "compass-blue.png"
    dark_source = allsky / "darks" / "2026-06-30" / "darkframe_20260630_000000.jpg"
    keogram_source = allsky / "images" / "2026-06-30" / "keogram_20260630.jpg"
    timelapse_source = allsky / "videos" / "timelapse_20260630.mp4"
    config_source = allsky / "config.sh"
    image_source.parent.mkdir(parents=True)
    html_asset.parent.mkdir(parents=True)
    overlay_asset.parent.mkdir(parents=True)
    dark_source.parent.mkdir(parents=True)
    timelapse_source.parent.mkdir(parents=True)
    Image.new("RGB", (64, 48), "navy").save(image_source)
    Image.new("RGB", (64, 48), "red").save(html_asset)
    Image.new("RGB", (64, 48), "blue").save(overlay_asset)
    Image.new("RGB", (64, 48), "black").save(dark_source)
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
            "SHOW_OVERLAY=true",
            "TEXTLINE1='Garden {captured_time}'",
            "TEXT_COLOR=#ffcc00",
            "FONT_SIZE=18",
            "RETENTION_DAYS=14",
            "PUBLIC_DAYS=5",
            "GENERATE_THUMBNAILS=true",
            "KEOGRAM=true",
            "STARTRAIL=true",
            "TIMELAPSE=true",
            "DAY_EXPOSURE=20",
            "DAY_GAIN=2",
            "DAY_INTERVAL=45",
            "SAVE_DAY=false",
            "CAPTURE_DAY=true",
            "NIGHT_EXPOSURE=12000",
            "NIGHT_GAIN=5",
            "NIGHT_INTERVAL=35",
            "SAVE_NIGHT=true",
            "CAPTURE_NIGHT=true",
            "END_OF_NIGHT_KEOGRAM=true",
            "END_OF_NIGHT_STARTRAIL=true",
            "END_OF_NIGHT_TIMELAPSE=true",
            "UNSUPPORTED_FOO=bar",
        ]),
        encoding="utf-8",
    )

    preview = client.post("/api/v1/migration/allsky/preview", headers=headers, json={"path": str(allsky)})
    assert preview.status_code == 200, preview.text
    preview_data = preview.json()["data"]
    assert preview_data["counts"] == {"images": 1, "timelapses": 1, "keograms": 1, "startrails": 0, "dark_frames": 1, "overlay_assets": 1}
    assert preview_data["unsupported_settings"][0]["path"] == str(config_source)
    assert preview_data["settings"]["observatory"]["name"] == "Garden Allsky"
    assert preview_data["settings"]["observatory"]["latitude"] == 49.1
    assert preview_data["settings"]["schedule"]["sun_angle"] == -12
    assert preview_data["settings"]["storage"]["retention_days"] == 14
    assert preview_data["settings"]["public_page"]["product_days"] == 5
    assert preview_data["settings"]["processing"]["keogram"] is True
    assert preview_data["settings"]["camera_profiles"]["daytime"]["interval_seconds"] == 45
    assert preview_data["settings"]["camera_profiles"]["daytime"]["save_enabled"] is False
    assert preview_data["settings"]["camera_profiles"]["nighttime"]["manual_exposure_ms"] == 12000
    assert preview_data["settings"]["camera_profiles"]["nighttime"]["end_of_night_timelapse"] is True
    assert preview_data["settings"]["overlay"]["enabled"] is True
    assert preview_data["settings"]["overlay"]["settings"]["lines"][0]["text"] == "Garden {captured_time}"
    assert any("UNSUPPORTED_FOO" in item.get("keys", []) for item in preview_data["unsupported_settings"])
    assert preview_data["will_delete_original"] is False

    queued = client.post("/api/v1/migration/allsky/import", headers=headers, json={"path": str(allsky)})
    assert queued.status_code == 200, queued.text
    job_id = queued.json()["data"]["id"]

    from skyweaver.services.processing import run_once

    assert asyncio.run(run_once()) is True
    completed = client.get(f"/api/v1/migration/jobs/{job_id}", headers=headers).json()["data"]
    assert completed["status"] == "completed"
    assert completed["output"]["imported_images"] == 1
    assert completed["output"]["imported_dark_frames"] == 1
    assert completed["output"]["imported_products"] == 2
    assert completed["output"]["imported_overlay_assets"] == 1
    assert {item["kind"] for item in completed["output"]["import_log"]} == {"image", "dark_frame", "keogram", "timelapse", "overlay_asset"}
    assert completed["output"]["settings"]["applied"]["camera_hints"]["hint"] == "IMX290"
    assert completed["output"]["settings"]["applied"]["overlay"]["settings"]["font_size"] == 18
    assert image_source.exists()
    assert dark_source.exists()
    assert keogram_source.exists()
    assert timelapse_source.exists()

    images = client.get("/api/v1/images", headers=headers).json()["data"]
    imported_image = next(item for item in images if item["metadata"]["migration"]["job_id"] == job_id)
    assert Path(imported_image["file_path"]).exists()
    assert imported_image["metadata"]["migration"]["original_path"] == str(image_source)
    products = client.get("/api/v1/products", headers=headers).json()["data"]
    imported_products = [item for item in products if item["metadata"]["migration"]["job_id"] == job_id]
    assert {item["type"] for item in imported_products} == {"keogram", "timelapse"}
    dark_frames = client.get("/api/v1/dark-frames", headers=headers).json()["data"]
    imported_dark = next(item for item in dark_frames if item["metadata"]["migration"]["job_id"] == job_id)
    assert imported_dark["metadata"]["migration"]["original_path"] == str(dark_source)
    copied_paths = [Path(imported_image["file_path"]), Path(imported_dark["file_path"]), *(Path(item["file_path"]) for item in imported_products)]
    overlay_asset_paths = [Path(path) for path in completed["output"]["overlay_asset_paths"]]
    assert all(path.exists() for path in copied_paths)
    assert len(overlay_asset_paths) == 1
    assert overlay_asset_paths[0].exists()
    settings_after_import = client.get("/api/v1/settings", headers=headers).json()["data"]
    assert settings_after_import["observatory"]["name"] == "Garden Allsky"
    assert settings_after_import["observatory"]["latitude"] == 49.1
    assert settings_after_import["observatory"]["longitude"] == 10.12
    assert settings_after_import["allsky_camera_hints"]["hint"] == "IMX290"
    assert settings_after_import["storage"]["retention_days"] == 14
    assert settings_after_import["public_page"]["product_days"] == 5
    assert settings_after_import["processing"]["startrails"] is True
    assert settings_after_import["allsky_overlay_assets"]["paths"] == [str(overlay_asset_paths[0])]
    profiles_after_import = client.get("/api/v1/camera-profiles", headers=headers).json()["data"]
    day_profile = next(item for item in profiles_after_import if item["mode"] == "daytime")
    night_profile = next(item for item in profiles_after_import if item["mode"] == "nighttime")
    assert day_profile["settings"]["interval_seconds"] == 45
    assert day_profile["settings"]["save_enabled"] is False
    assert night_profile["settings"]["manual_exposure_ms"] == 12000
    assert night_profile["settings"]["gain"] == 5
    assert night_profile["settings"]["end_of_night_startrail"] is True
    schedule_after_import = client.get("/api/v1/schedule", headers=headers).json()["data"]
    assert schedule_after_import["sun_angle"] == -12
    modules_after_import = client.get("/api/v1/modules", headers=headers).json()["data"]
    overlay_after_import = next(item for item in modules_after_import if item["id"] == "builtin.overlay")
    assert overlay_after_import["enabled"] is True
    assert overlay_after_import["settings"]["lines"][0]["text"] == "Garden {captured_time}"
    assert overlay_after_import["settings"]["text_color"] == "#ffcc00ff"

    rollback = client.post(f"/api/v1/migration/jobs/{job_id}/rollback", headers=headers)
    assert rollback.status_code == 200, rollback.text
    rollback_data = rollback.json()["data"]
    assert rollback_data["deleted_images"] == 1
    assert rollback_data["deleted_dark_frames"] == 1
    assert rollback_data["deleted_products"] == 2
    assert rollback_data["settings_restored"]["restored"] is True
    assert all(not path.exists() for path in copied_paths)
    assert all(not path.exists() for path in overlay_asset_paths)
    assert image_source.exists()
    assert dark_source.exists()
    assert keogram_source.exists()
    assert timelapse_source.exists()
    settings_after_rollback = client.get("/api/v1/settings", headers=headers).json()["data"]
    assert settings_after_rollback["observatory"]["name"] == "Sky Weaver Observatory"
    assert "allsky_camera_hints" not in settings_after_rollback
    assert "allsky_overlay_assets" not in settings_after_rollback
    assert settings_after_rollback["storage"]["retention_days"] == 30
    profiles_after_rollback = client.get("/api/v1/camera-profiles", headers=headers).json()["data"]
    day_after_rollback = next(item for item in profiles_after_rollback if item["mode"] == "daytime")
    assert day_after_rollback["settings"]["interval_seconds"] == 300
    schedule_after_rollback = client.get("/api/v1/schedule", headers=headers).json()["data"]
    assert schedule_after_rollback["sun_angle"] == -6
    modules_after_rollback = client.get("/api/v1/modules", headers=headers).json()["data"]
    overlay_after_rollback = next(item for item in modules_after_rollback if item["id"] == "builtin.overlay")
    assert overlay_after_rollback["enabled"] is False
    after_rollback_dark_frames = client.get("/api/v1/dark-frames", headers=headers).json()["data"]
    assert not any(item["metadata"].get("migration", {}).get("job_id") == job_id for item in after_rollback_dark_frames)
