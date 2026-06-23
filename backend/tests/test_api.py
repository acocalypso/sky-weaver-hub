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


def test_allsky_preview(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    allsky = tmp_path / "allsky"
    (allsky / "images").mkdir(parents=True)
    (allsky / "images" / "one.jpg").write_bytes(b"not-real-but-counted")
    res = client.post("/api/v1/migration/allsky/preview", headers={"Authorization": f"Bearer {token}"}, json={"path": str(allsky)})
    assert res.status_code == 200
    assert res.json()["data"]["counts"]["images"] == 1
