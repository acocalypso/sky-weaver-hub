import os
from pathlib import Path

from fastapi.testclient import TestClient


def make_client(tmp_path: Path):
    os.environ["SKYWEAVER_DATA_DIR"] = str(tmp_path / "data")
    os.environ["SKYWEAVER_CONFIG_DIR"] = str(tmp_path / "config")
    os.environ["SKYWEAVER_LOG_DIR"] = str(tmp_path / "logs")
    os.environ["SKYWEAVER_DB"] = str(tmp_path / "data" / "skyweaver.db")
    os.environ["SKYWEAVER_SECRET_KEY"] = "test-secret"
    from skyweaver.config import get_settings
    from skyweaver.main import create_app

    get_settings.cache_clear()
    return TestClient(create_app())


def login(client: TestClient) -> str:
    res = client.post("/api/v1/auth/login", json={"username": "admin", "password": "skyweaver-change-me"})
    assert res.status_code == 200, res.text
    return res.json()["data"]["token"]


def test_health_and_status(tmp_path):
    client = make_client(tmp_path)
    assert client.get("/api/v1/health").json()["data"]["status"] == "ok"
    token = login(client)
    res = client.get("/api/v1/status", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["data"]["camera"]["adapter"] == "mock"


def test_mock_capture_creates_image(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    res = client.post(
        "/api/v1/capture/test-shot",
        headers={"Authorization": f"Bearer {token}"},
        json={"exposure_ms": 500, "gain": 1, "format": "jpg", "mode": "manual"},
    )
    assert res.status_code == 200, res.text
    image = res.json()["data"]["image"]
    assert Path(image["file_path"]).exists()
    assert Path(image["file_path"] + ".json").exists()

    latest = client.get("/api/v1/images/latest", headers={"Authorization": f"Bearer {token}"})
    assert latest.status_code == 200
    assert latest.json()["data"]["id"] == image["id"]


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
