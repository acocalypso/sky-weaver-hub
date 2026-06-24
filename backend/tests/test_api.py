import asyncio
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient


def make_client(tmp_path: Path):
    os.environ["SKYWEAVER_DATA_DIR"] = str(tmp_path / "data")
    os.environ["SKYWEAVER_CONFIG_DIR"] = str(tmp_path / "config")
    os.environ["SKYWEAVER_LOG_DIR"] = str(tmp_path / "logs")
    os.environ["SKYWEAVER_DB"] = str(tmp_path / "data" / "skyweaver.db")
    os.environ["SKYWEAVER_SECRET_KEY"] = "test-secret-key-with-at-least-32-bytes"
    from skyweaver.config import get_settings
    from skyweaver.main import create_app

    get_settings.cache_clear()
    return TestClient(create_app())


def login(client: TestClient) -> str:
    res = client.post("/api/v1/auth/login", json={"username": "admin", "password": "skyweaver-change-me"})
    assert res.status_code == 200, res.text
    return res.json()["data"]["token"]


def run_queued_test_capture(client: TestClient, headers: dict[str, str], payload: dict):
    queued_res = client.post("/api/v1/capture/test-shot", headers=headers, json=payload)
    assert queued_res.status_code == 200, queued_res.text
    queued = queued_res.json()["data"]
    assert queued["type"] == "test"
    assert queued["status"] == "pending"

    from skyweaver.capture_daemon import CaptureDaemon

    assert asyncio.run(CaptureDaemon().run_once()) is True
    job = client.get(f"/api/v1/capture/jobs/{queued['id']}", headers=headers).json()["data"]
    assert job["status"] == "completed"
    latest = client.get("/api/v1/images/latest", headers=headers).json()["data"]
    assert latest["id"] == job["result"]["image_id"]
    return queued, job, latest


def test_health_and_status(tmp_path):
    client = make_client(tmp_path)
    assert client.get("/api/v1/health").json()["data"]["status"] == "ok"
    token = login(client)
    res = client.get("/api/v1/status", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["data"]["camera"]["adapter"] == "mock"


def test_mock_capture_creates_image(tmp_path):
    client = make_client(tmp_path)
    latest_dir = tmp_path / "data" / "latest"
    stale_thumbnail = latest_dir / "latest-thumbnail.png"
    stale_thumbnail.write_bytes(b"stale")
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    _queued, _job, image = run_queued_test_capture(client, headers, {"exposure_ms": 500, "gain": 1, "format": "jpg", "mode": "manual"})
    assert Path(image["file_path"]).exists()
    assert Path(image["file_path"] + ".json").exists()

    latest = client.get("/api/v1/images/latest", headers=headers)
    assert latest.status_code == 200
    assert latest.json()["data"]["id"] == image["id"]

    latest_file = latest_dir / "latest.jpg"
    latest_thumb = latest_dir / "latest-thumbnail.jpg"
    latest_json = latest_dir / "latest.json"
    assert latest_file.exists()
    assert latest_file.read_bytes() == Path(image["file_path"]).read_bytes()
    assert latest_thumb.exists()
    assert not stale_thumbnail.exists()
    assert latest_json.exists()
    latest_payload = json.loads(latest_json.read_text(encoding="utf-8"))
    assert latest_payload["id"] == image["id"]
    assert latest_payload["download_url"] == "/api/v1/public/latest/download"


def test_public_latest_endpoints_are_unauthenticated(tmp_path):
    client = make_client(tmp_path)
    assert client.get("/api/v1/public/latest").status_code == 404

    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    _queued, _job, image = run_queued_test_capture(client, headers, {"exposure_ms": 500, "gain": 1, "format": "jpg", "mode": "manual"})

    public_latest = client.get("/api/v1/public/latest")
    assert public_latest.status_code == 200
    public_data = public_latest.json()["data"]
    assert public_data["id"] == image["id"]
    assert public_data["download_url"] == "/api/v1/public/latest/download"
    assert public_data["thumbnail_url"] == "/api/v1/public/latest/thumbnail"
    assert "file_path" not in public_data

    public_download = client.get("/api/v1/public/latest/download")
    assert public_download.status_code == 200
    assert public_download.content == Path(image["file_path"]).read_bytes()

    public_thumbnail = client.get("/api/v1/public/latest/thumbnail")
    assert public_thumbnail.status_code == 200
    assert public_thumbnail.content == Path(image["thumbnail_path"]).read_bytes()


def test_api_key_scopes(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    key_res = client.post(
        "/api/v1/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "mobile", "scopes": ["read:status", "read:images"]},
    )
    assert key_res.status_code == 200
    api_key = key_res.json()["data"]["key"]
    assert client.get("/api/v1/status", headers={"Authorization": f"Bearer {api_key}"}).status_code == 200
    assert client.post("/api/v1/capture/start", headers={"Authorization": f"Bearer {api_key}"}).status_code == 403


def test_setup_environment_seeds_admin_camera_schedule_and_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("SKYWEAVER_ADMIN_USERNAME", "setup-admin")
    monkeypatch.setenv("SKYWEAVER_ADMIN_PASSWORD", "setup-secret")
    monkeypatch.setenv("SKYWEAVER_OBSERVATORY_NAME", "Back Garden")
    monkeypatch.setenv("SKYWEAVER_OBSERVATORY_LATITUDE", "47.1234")
    monkeypatch.setenv("SKYWEAVER_OBSERVATORY_LONGITUDE", "15.5678")
    monkeypatch.setenv("SKYWEAVER_OBSERVATORY_TIMEZONE", "Europe/Berlin")
    monkeypatch.setenv("SKYWEAVER_PRIMARY_CAMERA_ADAPTER", "rpicam")
    monkeypatch.setenv("SKYWEAVER_PUBLIC_PAGE_ENABLED", "0")
    monkeypatch.setenv("SKYWEAVER_FIRST_SETUP_REQUIRED", "0")

    client = make_client(tmp_path)
    res = client.post("/api/v1/auth/login", json={"username": "setup-admin", "password": "setup-secret"})
    assert res.status_code == 200, res.text
    token = res.json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    cameras = client.get("/api/v1/cameras", headers=headers).json()["data"]
    assert cameras[0]["adapter"] == "rpicam"

    schedule = client.get("/api/v1/schedule", headers=headers).json()["data"]
    assert schedule["timezone"] == "Europe/Berlin"
    assert schedule["latitude"] == 47.1234
    assert schedule["longitude"] == 15.5678

    settings = client.get("/api/v1/settings", headers=headers).json()["data"]
    assert settings["observatory"]["name"] == "Back Garden"
    assert settings["observatory"]["timezone"] == "Europe/Berlin"
    assert settings["public_page"]["enabled"] is False
    assert settings["security"]["first_setup_required"] is False


def test_first_setup_status_and_completion(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    status = client.get("/api/v1/setup/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["data"]["required"] is True

    cameras = client.get("/api/v1/cameras", headers=headers).json()["data"]
    res = client.post(
        "/api/v1/setup/complete",
        headers=headers,
        json={
            "admin_password": "New-setup-secret-2026",
            "observatory_name": "Garden Pier",
            "latitude": 47.25,
            "longitude": 15.5,
            "timezone": "Europe/Berlin",
            "public_page_enabled": False,
            "primary_camera_id": cameras[0]["id"],
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["required"] is False

    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "skyweaver-change-me"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "New-setup-secret-2026"}).status_code == 200

    after = client.get("/api/v1/setup/status", headers=headers).json()["data"]
    assert after["required"] is False
    settings = client.get("/api/v1/settings", headers=headers).json()["data"]
    assert settings["observatory"]["name"] == "Garden Pier"
    assert settings["security"]["first_setup_required"] is False
    assert settings["public_page"]["enabled"] is False
    schedule = client.get("/api/v1/schedule", headers=headers).json()["data"]
    assert schedule["timezone"] == "Europe/Berlin"
    assert schedule["latitude"] == 47.25


def test_first_setup_remains_required_for_bootstrap_password(tmp_path, monkeypatch):
    monkeypatch.setenv("SKYWEAVER_FIRST_SETUP_REQUIRED", "0")
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    status = client.get("/api/v1/setup/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["data"]["required"] is True
    assert status.json()["data"]["bootstrap_password_active"] is True

    weak = client.post(
        "/api/v1/setup/complete",
        headers=headers,
        json={
            "admin_password": "skyweaver-change-me",
            "observatory_name": "Garden Pier",
            "latitude": 47.25,
            "longitude": 15.5,
            "timezone": "Europe/Berlin",
            "public_page_enabled": False,
        },
    )
    assert weak.status_code == 400

    missing_password = client.post(
        "/api/v1/setup/complete",
        headers=headers,
        json={
            "observatory_name": "Garden Pier",
            "latitude": 47.25,
            "longitude": 15.5,
            "timezone": "Europe/Berlin",
            "public_page_enabled": False,
        },
    )
    assert missing_password.status_code == 400


def test_first_setup_rejects_password_over_bcrypt_limit(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/api/v1/setup/complete",
        headers=headers,
        json={
            "admin_password": "A" * 73,
            "observatory_name": "Garden Pier",
            "latitude": 47.25,
            "longitude": 15.5,
            "timezone": "Europe/Berlin",
            "public_page_enabled": False,
        },
    )

    assert res.status_code == 400
    assert "72 bytes or fewer" in res.text


def test_login_failures_are_rate_limited_and_success_resets(tmp_path):
    client = make_client(tmp_path)
    payload = {"username": "admin", "password": "not-the-password"}

    for _ in range(5):
        res = client.post("/api/v1/auth/login", json=payload)
        assert res.status_code == 401

    limited = client.post("/api/v1/auth/login", json=payload)
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0
    assert "Too many failed attempts" in limited.json()["error"]["message"]

    other_user = client.post("/api/v1/auth/login", json={"username": "operator", "password": "not-the-password"})
    assert other_user.status_code == 401

    fresh_client = make_client(tmp_path / "fresh")
    assert fresh_client.post("/api/v1/auth/login", json={"username": "admin", "password": "skyweaver-change-me"}).status_code == 200
    assert fresh_client.post("/api/v1/auth/login", json=payload).status_code == 401
    assert fresh_client.post("/api/v1/auth/login", json={"username": "admin", "password": "skyweaver-change-me"}).status_code == 200
    for _ in range(5):
        assert fresh_client.post("/api/v1/auth/login", json=payload).status_code == 401
    assert fresh_client.post("/api/v1/auth/login", json=payload).status_code == 429


def test_setup_completion_failures_are_rate_limited(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "admin_password": "skyweaver-change-me",
        "observatory_name": "Garden Pier",
        "latitude": 47.25,
        "longitude": 15.5,
        "timezone": "Europe/Berlin",
        "public_page_enabled": False,
    }

    for _ in range(5):
        res = client.post("/api/v1/setup/complete", headers=headers, json=payload)
        assert res.status_code == 400

    limited = client.post("/api/v1/setup/complete", headers=headers, json=payload)
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0
    assert "Too many failed attempts" in limited.json()["error"]["message"]


def test_system_diagnostics_export_is_redacted(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    res = client.get("/api/v1/system/diagnostics", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["app"]["name"] == "Sky Weaver Hub"
    assert data["metrics"]["disk_free_gb"] >= 0
    assert any(service["name"] == "skyweaver-api" for service in data["services"])
    assert "counts" in data
    assert "password_hash" not in res.text
    assert "key_hash" not in res.text
    assert "dev-change-me" not in res.text


def test_system_service_control_runs_allowlisted_actions(tmp_path, monkeypatch):
    from skyweaver.api import routes

    client = make_client(tmp_path)
    token = login(client)
    calls = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **_kwargs):
        calls.append(command)
        return Result()

    monkeypatch.setattr(routes, "systemctl_command", lambda: ["systemctl"])
    monkeypatch.setattr(routes.subprocess, "run", fake_run)

    res = client.post("/api/v1/system/services/skyweaver-capture/restart", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "completed"
    assert calls == [["systemctl", "restart", "skyweaver-capture.service"]]

    assert client.post("/api/v1/system/services/not-skyweaver/restart", headers={"Authorization": f"Bearer {token}"}).status_code == 404
    assert client.post("/api/v1/system/services/skyweaver-capture/reload", headers={"Authorization": f"Bearer {token}"}).status_code == 400


def test_system_service_detail_includes_status_and_journal(tmp_path, monkeypatch):
    from skyweaver.api import routes

    client = make_client(tmp_path)
    token = login(client)
    calls = []

    class Result:
        def __init__(self, stdout: str):
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def fake_run(command, **_kwargs):
        calls.append(command)
        if "show" in command:
            return Result("Id=skyweaver-capture.service\nActiveState=active\nMainPID=123\n")
        return Result("2026-06-24T05:00:00 skyweaver-capture started\n")

    monkeypatch.setattr(routes, "systemctl_command", lambda: ["systemctl"])
    monkeypatch.setattr(routes.shutil, "which", lambda name: "journalctl" if name == "journalctl" else None)
    monkeypatch.setattr(routes.subprocess, "run", fake_run)

    res = client.get("/api/v1/system/services/skyweaver-capture", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["unit"] == "skyweaver-capture.service"
    assert data["systemctl_status"] == "ok"
    assert data["properties"]["ActiveState"] == "active"
    assert data["journal_status"] == "ok"
    assert data["journal"] == ["2026-06-24T05:00:00 skyweaver-capture started"]
    assert calls[0] == ["systemctl", "show", "skyweaver-capture.service", "--no-pager", "--property=Id,Description,LoadState,ActiveState,SubState,UnitFileState,MainPID,ExecMainStatus,ExecMainCode,Restart,NRestarts,FragmentPath,DropInPaths"]
    assert calls[1] == ["journalctl", "-u", "skyweaver-capture.service", "-n", "80", "--no-pager", "--output=short-iso"]
    assert client.get("/api/v1/system/services/not-skyweaver", headers={"Authorization": f"Bearer {token}"}).status_code == 404


def test_system_service_control_queues_api_restart(tmp_path, monkeypatch):
    from skyweaver.api import routes

    client = make_client(tmp_path)
    token = login(client)
    calls = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **_kwargs):
        calls.append(command)
        return Result()

    monkeypatch.setattr(routes, "systemctl_command", lambda: ["sudo", "-n", "/usr/bin/systemctl"])
    monkeypatch.setattr(routes.subprocess, "run", fake_run)

    res = client.post("/api/v1/system/services/skyweaver-api/restart", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "queued"
    assert calls == [["sudo", "-n", "/usr/bin/systemctl", "--no-block", "restart", "skyweaver-api.service"]]


def test_system_service_control_requires_admin_scope(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    key_res = client.post(
        "/api/v1/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "readonly", "scopes": ["read:status"]},
    )
    api_key = key_res.json()["data"]["key"]
    res = client.post("/api/v1/system/services/skyweaver-capture/restart", headers={"Authorization": f"Bearer {api_key}"})
    assert res.status_code == 403


def test_allsky_preview(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    allsky = tmp_path / "allsky"
    (allsky / "images").mkdir(parents=True)
    (allsky / "images" / "one.jpg").write_bytes(b"not-real-but-counted")
    res = client.post("/api/v1/migration/allsky/preview", headers={"Authorization": f"Bearer {token}"}, json={"path": str(allsky)})
    assert res.status_code == 200
    assert res.json()["data"]["counts"]["images"] == 1
