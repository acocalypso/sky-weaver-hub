import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
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


def test_frontend_deep_links_fall_back_to_index(tmp_path):
    web_dir = tmp_path / "data" / "web"
    web_dir.mkdir(parents=True)
    (web_dir / "index.html").write_text("<!doctype html><title>Sky Weaver</title><div id=\"root\"></div>", encoding="utf-8")
    (web_dir / "app.js").write_text("console.log('skyweaver')", encoding="utf-8")

    client = make_client(tmp_path)
    public_res = client.get("/public", headers={"accept": "text/html"})
    assert public_res.status_code == 200
    assert "Sky Weaver" in public_res.text

    assert client.get("/app.js").status_code == 200
    assert client.get("/missing.js", headers={"accept": "application/javascript"}).status_code == 404
    assert client.get("/api/v1/health").json()["data"]["status"] == "ok"


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
    assert image["metadata"]["storage"]["image"]["width"] == image["width"]
    assert image["metadata"]["storage"]["image"]["height"] == image["height"]
    assert image["metadata"]["storage"]["file"]["size_bytes"] == image["size_bytes"]
    assert image["metadata"]["storage"]["exif"] == {}
    sidecar = json.loads(Path(image["file_path"] + ".json").read_text(encoding="utf-8"))
    assert sidecar["storage"]["image"]["format"] == "JPEG"


def test_extract_image_metadata_reads_exif_and_basic_file_data(tmp_path):
    from PIL import ExifTags, Image
    from skyweaver.services.capture import extract_image_metadata

    path = tmp_path / "exif-test.jpg"
    img = Image.new("RGB", (12, 8), "black")
    exif = Image.Exif()
    exif[ExifTags.Base.Make.value] = "Sky Weaver"
    exif[ExifTags.Base.Model.value] = "MockCam"
    img.save(path, exif=exif)

    metadata = extract_image_metadata(path)

    assert metadata["file"]["name"] == "exif-test.jpg"
    assert metadata["file"]["size_bytes"] == path.stat().st_size
    assert metadata["image"]["format"] == "JPEG"
    assert metadata["image"]["width"] == 12
    assert metadata["image"]["height"] == 8
    assert metadata["exif"]["Make"] == "Sky Weaver"
    assert metadata["exif"]["Model"] == "MockCam"


def test_delete_image_removes_files_row_and_matching_latest(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    _queued, _job, image = run_queued_test_capture(client, headers, {"exposure_ms": 500, "gain": 1, "format": "jpg", "mode": "manual"})

    file_path = Path(image["file_path"])
    sidecar_path = Path(image["file_path"] + ".json")
    thumbnail_path = Path(image["thumbnail_path"])
    latest_dir = tmp_path / "data" / "latest"
    latest_file = latest_dir / "latest.jpg"
    latest_thumb = latest_dir / "latest-thumbnail.jpg"
    latest_json = latest_dir / "latest.json"
    assert file_path.exists()
    assert sidecar_path.exists()
    assert thumbnail_path.exists()
    assert latest_file.exists()
    assert latest_thumb.exists()
    assert latest_json.exists()

    delete_res = client.delete(f"/api/v1/images/{image['id']}", headers=headers)
    assert delete_res.status_code == 200, delete_res.text
    payload = delete_res.json()["data"]
    assert payload["deleted"] == image["id"]
    assert str(file_path) in payload["deleted_files"]
    assert str(sidecar_path) in payload["deleted_files"]
    assert str(thumbnail_path) in payload["deleted_files"]
    assert str(latest_file) in payload["deleted_files"]
    assert str(latest_thumb) in payload["deleted_files"]
    assert str(latest_json) in payload["deleted_files"]
    assert client.get(f"/api/v1/images/{image['id']}", headers=headers).status_code == 404
    for path in (file_path, sidecar_path, thumbnail_path, latest_file, latest_thumb, latest_json):
        assert not path.exists()
    assert client.get("/api/v1/public/latest").status_code == 404


def test_image_retention_cleanup_removes_old_images_only(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    _queued_old, _job_old, old_image = run_queued_test_capture(client, headers, {"exposure_ms": 500, "gain": 1, "format": "jpg", "mode": "manual"})
    _queued_new, _job_new, new_image = run_queued_test_capture(client, headers, {"exposure_ms": 500, "gain": 1, "format": "jpg", "mode": "manual"})
    old_file = Path(old_image["file_path"])
    new_file = Path(new_image["file_path"])

    from skyweaver.db import session

    with session() as conn:
        conn.execute(
            "UPDATE images SET captured_at=?, day_key=? WHERE id=?",
            ("2020-01-01T00:00:00+00:00", "20200101", old_image["id"]),
        )

    cleanup_res = client.post("/api/v1/images/retention/run?days=30", headers=headers)
    assert cleanup_res.status_code == 200, cleanup_res.text
    payload = cleanup_res.json()["data"]
    assert payload["retention_days"] == 30
    assert payload["deleted_images"] == 1
    assert payload["deleted_image_ids"] == [old_image["id"]]
    assert str(old_file) in payload["deleted_files"]
    assert not old_file.exists()
    assert not Path(old_image["thumbnail_path"]).exists()
    assert not Path(old_image["file_path"] + ".json").exists()
    assert new_file.exists()
    assert client.get(f"/api/v1/images/{new_image['id']}", headers=headers).status_code == 200
    assert client.get("/api/v1/public/latest").json()["data"]["id"] == new_image["id"]


def test_builtin_overlay_module_can_render_on_capture(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    modules = client.get("/api/v1/modules", headers=headers)
    assert modules.status_code == 200, modules.text
    overlay = next(row for row in modules.json()["data"] if row["id"] == "builtin.overlay")
    assert overlay["trusted"] is True
    assert overlay["enabled"] is False
    assert overlay["module_path"] is None

    patch_res = client.patch(
        "/api/v1/modules/builtin.overlay",
        headers=headers,
        json={
            "enabled": True,
            "settings": {
                "lines": [{"text": "Sky Weaver {mode} {exposure_ms}", "position": "center"}],
                "font_size": 20,
                "margin": 4,
                "padding": 4,
                "text_color": "#ffffffff",
                "background_color": "#000000cc",
            },
        },
    )
    assert patch_res.status_code == 200, patch_res.text
    assert patch_res.json()["data"]["enabled"] is True

    _queued, _job, image = run_queued_test_capture(client, headers, {"exposure_ms": 500, "gain": 1, "format": "jpg", "mode": "manual"})
    assert image["overlay_applied"] is True
    assert image["metadata"]["overlay"]["applied"] is True
    assert image["metadata"]["overlay"]["lines"] == 1
    assert image["metadata"]["storage"]["file"]["size_bytes"] == image["size_bytes"]

    sidecar = json.loads(Path(image["file_path"] + ".json").read_text(encoding="utf-8"))
    assert sidecar["overlay"]["applied"] is True

    delete_res = client.delete("/api/v1/modules/builtin.overlay", headers=headers)
    assert delete_res.status_code == 403


def test_post_capture_flow_controls_overlay_application(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    flows = client.get("/api/v1/module-flows", headers=headers)
    assert flows.status_code == 200, flows.text
    flow = next(row for row in flows.json()["data"] if row["id"] == "builtin.post_capture")
    assert flow["enabled"] is True
    assert flow["module_order"] == ["builtin.overlay"]

    assert client.patch("/api/v1/modules/builtin.overlay", headers=headers, json={"enabled": True}).status_code == 200

    run_res = client.post("/api/v1/module-flows/builtin.post_capture/run", headers=headers)
    assert run_res.status_code == 200, run_res.text
    run_data = run_res.json()["data"]
    assert run_data["status"] == "completed"
    assert run_data["modules"][0]["id"] == "builtin.overlay"
    assert run_data["modules"][0]["status"] == "ready"

    disabled = client.patch("/api/v1/module-flows/builtin.post_capture", headers=headers, json={"enabled": False})
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["data"]["enabled"] is False

    _queued, _job, image = run_queued_test_capture(client, headers, {"exposure_ms": 500, "gain": 1, "format": "jpg", "mode": "manual"})
    assert image["overlay_applied"] is False
    assert image["metadata"]["overlay"]["applied"] is False

    invalid = client.patch("/api/v1/module-flows/builtin.post_capture", headers=headers, json={"module_order": ["missing.module"]})
    assert invalid.status_code == 404


def test_external_module_manifest_registers_but_cannot_execute(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    registered = client.post(
        "/api/v1/modules/register",
        headers=headers,
        json={
            "id": "external.sample-overlay",
            "name": "Sample external overlay",
            "description": "Manifest-only module package.",
            "version": "0.1.0",
            "author": "Sky Weaver Test",
            "capabilities": ["post_capture"],
            "settings_schema": {"type": "object"},
            "settings": {"example": True},
        },
    )

    assert registered.status_code == 200, registered.text
    module = registered.json()["data"]
    assert module["id"] == "external.sample-overlay"
    assert module["enabled"] is False
    assert module["trusted"] is False
    assert module["module_path"] == "external:external.sample-overlay"

    enable_res = client.patch("/api/v1/modules/external.sample-overlay", headers=headers, json={"enabled": True})
    assert enable_res.status_code == 403

    flow_res = client.patch(
        "/api/v1/module-flows/builtin.post_capture",
        headers=headers,
        json={"module_order": ["builtin.overlay", "external.sample-overlay"]},
    )
    assert flow_res.status_code == 403

    deleted = client.delete("/api/v1/modules/external.sample-overlay", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"]["deleted"] == "external.sample-overlay"


def test_deleting_latest_republishes_next_newest_image(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    _queued_old, _job_old, old_image = run_queued_test_capture(client, headers, {"exposure_ms": 500, "gain": 1, "format": "jpg", "mode": "manual"})
    _queued_new, _job_new, new_image = run_queued_test_capture(client, headers, {"exposure_ms": 500, "gain": 1, "format": "jpg", "mode": "manual"})

    delete_res = client.delete(f"/api/v1/images/{new_image['id']}", headers=headers)
    assert delete_res.status_code == 200, delete_res.text
    payload = delete_res.json()["data"]
    assert payload["latest_republished"]["id"] == old_image["id"]

    public_latest = client.get("/api/v1/public/latest")
    assert public_latest.status_code == 200
    assert public_latest.json()["data"]["id"] == old_image["id"]
    public_download = client.get("/api/v1/public/latest/download")
    assert public_download.status_code == 200
    assert public_download.content == Path(old_image["file_path"]).read_bytes()


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
    assert public_data["exposure_ms"] == image["exposure_ms"]
    assert public_data["gain"] == image["gain"]
    assert "file_path" not in public_data

    public_download = client.get("/api/v1/public/latest/download")
    assert public_download.status_code == 200
    assert public_download.content == Path(image["file_path"]).read_bytes()

    public_thumbnail = client.get("/api/v1/public/latest/thumbnail")
    assert public_thumbnail.status_code == 200
    assert public_thumbnail.content == Path(image["thumbnail_path"]).read_bytes()


def test_public_latest_endpoints_honor_public_page_setting(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    _queued, _job, image = run_queued_test_capture(client, headers, {"exposure_ms": 500, "gain": 1, "format": "jpg", "mode": "manual"})

    settings_res = client.patch("/api/v1/settings", headers=headers, json={"values": {"public_page": {"enabled": False, "iframe_enabled": True}}})
    assert settings_res.status_code == 200, settings_res.text

    public_latest = client.get("/api/v1/public/latest")
    assert public_latest.status_code == 403
    assert "Public page is disabled" in public_latest.text
    assert client.get("/api/v1/public/latest/download").status_code == 403
    assert client.get("/api/v1/public/latest/thumbnail").status_code == 403

    authed_latest = client.get("/api/v1/images/latest", headers=headers)
    assert authed_latest.status_code == 200
    assert authed_latest.json()["data"]["id"] == image["id"]


def test_public_products_are_safe_unauthenticated_and_visibility_limited(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    products_dir = tmp_path / "data" / "products"
    products_dir.mkdir(parents=True, exist_ok=True)
    recent_file = products_dir / "keogram.jpg"
    recent_thumbnail = products_dir / "keogram-thumb.jpg"
    old_file = products_dir / "old-startrail.jpg"
    recent_file.write_bytes(b"recent-product")
    recent_thumbnail.write_bytes(b"recent-thumb")
    old_file.write_bytes(b"old-product")

    from skyweaver.db import json_dumps, session

    recent_id = "public-product-recent"
    old_id = "public-product-old"
    recent_at = datetime.now(UTC).isoformat()
    old_at = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    with session() as conn:
        conn.execute(
            "INSERT INTO night_products (id, type, day_key, file_path, thumbnail_path, status, metadata, created_at) VALUES (?, 'keogram', '20260630', ?, ?, 'completed', ?, ?)",
            (recent_id, str(recent_file), str(recent_thumbnail), json_dumps({"source_images": 42, "private_path": "/secret"}), recent_at),
        )
        conn.execute(
            "INSERT INTO night_products (id, type, day_key, file_path, thumbnail_path, status, metadata, created_at) VALUES (?, 'startrail', '20260620', ?, NULL, 'completed', ?, ?)",
            (old_id, str(old_file), json_dumps({"source_images": 99}), old_at),
        )
    settings_res = client.patch("/api/v1/settings", headers=headers, json={"values": {"public_page": {"enabled": True, "iframe_enabled": True, "product_days": 7}}})
    assert settings_res.status_code == 200, settings_res.text

    public_products = client.get("/api/v1/public/products")
    assert public_products.status_code == 200, public_products.text
    payload = public_products.json()["data"]
    assert payload["configured_days"] == 7
    assert [item["id"] for item in payload["products"]] == [recent_id]
    product = payload["products"][0]
    assert product["download_url"] == f"/api/v1/public/products/{recent_id}/download"
    assert product["thumbnail_url"] == f"/api/v1/public/products/{recent_id}/thumbnail"
    assert product["metadata"] == {"source_images": 42}
    assert "file_path" not in product
    assert "thumbnail_path" not in product

    assert client.get(f"/api/v1/public/products/{recent_id}/download").content == b"recent-product"
    assert client.get(f"/api/v1/public/products/{recent_id}/thumbnail").content == b"recent-thumb"
    assert client.get(f"/api/v1/public/products/{old_id}/download").status_code == 404

    disable_res = client.patch("/api/v1/settings", headers=headers, json={"values": {"public_page": {"enabled": False, "iframe_enabled": True, "product_days": 7}}})
    assert disable_res.status_code == 200, disable_res.text
    assert client.get("/api/v1/public/products").status_code == 403
    assert client.get(f"/api/v1/public/products/{recent_id}/download").status_code == 403


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


def test_created_camera_gets_day_and_night_profiles(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "IMX290", "adapter": "rpicam", "device_id": "rpicam://0", "model": "imx290", "enabled": True, "is_primary": True},
    )
    assert created.status_code == 200, created.text
    camera_id = created.json()["data"]["id"]

    profiles = client.get("/api/v1/camera-profiles", headers=headers).json()["data"]
    camera_profiles = [profile for profile in profiles if profile["camera_id"] == camera_id]
    assert {profile["mode"] for profile in camera_profiles} == {"daytime", "nighttime"}
    assert next(profile for profile in camera_profiles if profile["mode"] == "daytime")["settings"]["interval_seconds"] == 300
    assert next(profile for profile in camera_profiles if profile["mode"] == "nighttime")["settings"]["capture_enabled"] is True


def test_camera_profiles_endpoint_backfills_missing_default_profiles(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    from skyweaver.db import session

    with session() as conn:
        camera = conn.execute("SELECT id FROM cameras WHERE is_primary=1 LIMIT 1").fetchone()
        conn.execute("DELETE FROM camera_profiles WHERE camera_id=? AND mode='daytime'", (camera["id"],))
        camera_id = camera["id"]

    profiles = client.get("/api/v1/camera-profiles", headers=headers).json()["data"]
    camera_profiles = [profile for profile in profiles if profile["camera_id"] == camera_id]
    assert {profile["mode"] for profile in camera_profiles} >= {"daytime", "nighttime"}


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

    logs = client.get("/api/v1/logs?source=security", headers=headers)
    assert logs.status_code == 200
    setup_log = next(row for row in logs.json()["data"] if row["message"] == "First setup completed")
    assert setup_log["context"]["password_changed"] is True
    assert setup_log["context"]["primary_camera_id"] == cameras[0]["id"]
    assert "New-setup-secret-2026" not in logs.text


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

    from skyweaver.db import session
    from skyweaver.services.capture import all_rows

    with session() as conn:
        logs = all_rows(conn, "SELECT * FROM logs WHERE source='auth' ORDER BY created_at")
    assert [row["message"] for row in logs].count("Login failed") == 6
    assert logs[-2]["context"]["failure_count"] == 5
    assert logs[-1]["message"] == "Login failed"
    assert logs[-1]["context"]["identifier"] == "operator"
    blocked = [row for row in logs if row["message"] == "Login blocked by rate limit"]
    assert len(blocked) == 1
    assert blocked[0]["context"]["failure_count"] == 5
    assert blocked[0]["context"]["rate_limited"] is True
    assert "not-the-password" not in json.dumps(logs)

    fresh_client = make_client(tmp_path / "fresh")
    assert fresh_client.post("/api/v1/auth/login", json={"username": "admin", "password": "skyweaver-change-me"}).status_code == 200
    assert fresh_client.post("/api/v1/auth/login", json=payload).status_code == 401
    assert fresh_client.post("/api/v1/auth/login", json={"username": "admin", "password": "skyweaver-change-me"}).status_code == 200
    with session() as conn:
        fresh_logs = all_rows(conn, "SELECT * FROM logs WHERE source='auth' ORDER BY created_at")
    assert any(row["message"] == "Login succeeded after previous failures" and row["context"]["failure_count"] == 1 for row in fresh_logs)
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

    logs = client.get("/api/v1/logs?source=auth", headers=headers)
    assert logs.status_code == 200
    auth_logs = logs.json()["data"]
    setup_logs = [row for row in auth_logs if row["message"] == "Setup completion failed"]
    assert len(setup_logs) == 5
    assert setup_logs[0]["context"]["reason"] == "password_policy"
    assert max(row["context"]["failure_count"] for row in setup_logs) == 5
    blocked = [row for row in auth_logs if row["message"] == "Setup completion blocked by rate limit"]
    assert len(blocked) == 1
    assert blocked[0]["context"]["failure_count"] == 5
    assert blocked[0]["context"]["rate_limited"] is True
    assert "skyweaver-change-me" not in logs.text


def test_user_and_api_key_lifecycle_are_security_audited_without_secrets(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    password_res = client.patch("/api/v1/users/me/password", headers=headers, json={"username": "admin", "password": "New-admin-secret-2026!"})
    assert password_res.status_code == 200, password_res.text

    user_res = client.post("/api/v1/users", headers=headers, json={"username": "operator-audit", "password": "Operator-secret-2026!"})
    assert user_res.status_code == 200, user_res.text
    user_id = user_res.json()["data"]["id"]
    assert client.patch(f"/api/v1/users/{user_id}", headers=headers, json={"role": "viewer"}).status_code == 200
    assert client.delete(f"/api/v1/users/{user_id}", headers=headers).status_code == 200

    key_res = client.post(
        "/api/v1/api-keys",
        headers=headers,
        json={"name": "mobile-audit", "scopes": ["read:status", "read:images"]},
    )
    assert key_res.status_code == 200, key_res.text
    key_data = key_res.json()["data"]
    assert client.patch(f"/api/v1/api-keys/{key_data['id']}", headers=headers, json={"enabled": False}).status_code == 200
    assert client.delete(f"/api/v1/api-keys/{key_data['id']}", headers=headers).status_code == 200

    logs = client.get("/api/v1/logs?source=security", headers=headers)
    assert logs.status_code == 200, logs.text
    messages = [row["message"] for row in logs.json()["data"]]
    assert "Password changed" in messages
    assert "User created" in messages
    assert "User updated" in messages
    assert "User deleted" in messages
    assert "API key created" in messages
    assert "API key updated" in messages
    assert "API key deleted" in messages
    assert key_data["key"] not in logs.text
    assert "Operator-secret-2026!" not in logs.text
    assert "New-admin-secret-2026!" not in logs.text
    assert "key_hash" not in logs.text

    created_key_log = next(row for row in logs.json()["data"] if row["message"] == "API key created")
    assert created_key_log["context"]["api_key_id"] == key_data["id"]
    assert created_key_log["context"]["prefix"] == key_data["prefix"]
    assert created_key_log["context"]["scopes"] == ["read:status", "read:images"]
    assert created_key_log["context"]["principal_username"] == "admin"


def test_privileged_settings_schedule_and_camera_changes_are_security_audited(tmp_path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    settings_res = client.patch(
        "/api/v1/settings",
        headers=headers,
        json={"values": {"remote_upload": {"enabled": True, "password": "remote-secret-value"}, "observatory": {"name": "Audit Garden"}}},
    )
    assert settings_res.status_code == 200, settings_res.text

    schedule_res = client.put("/api/v1/schedule", headers=headers, json={"enabled": True, "interval_seconds": 45, "timezone": "Europe/Berlin"})
    assert schedule_res.status_code == 200, schedule_res.text

    camera_res = client.post(
        "/api/v1/cameras",
        headers=headers,
        json={"name": "Audit Cam", "adapter": "mock", "device_id": "mock://audit", "model": "mock-audit", "enabled": True, "is_primary": False},
    )
    assert camera_res.status_code == 200, camera_res.text
    camera_id = camera_res.json()["data"]["id"]
    assert client.patch(f"/api/v1/cameras/{camera_id}", headers=headers, json={"enabled": False}).status_code == 200

    profile_res = client.post(
        "/api/v1/camera-profiles",
        headers=headers,
        json={"camera_id": camera_id, "name": "Audit Night", "mode": "nighttime", "settings": {"exposure_ms": 15000, "api_key": "profile-secret-value"}},
    )
    assert profile_res.status_code == 200, profile_res.text
    profile_id = profile_res.json()["data"]["id"]
    assert client.patch(f"/api/v1/camera-profiles/{profile_id}", headers=headers, json={"settings": {"gain": 4}}).status_code == 200

    logs = client.get("/api/v1/logs?source=security", headers=headers)
    assert logs.status_code == 200, logs.text
    rows = logs.json()["data"]
    messages = [row["message"] for row in rows]
    assert "Settings updated" in messages
    assert "Schedule updated" in messages
    assert "Camera created" in messages
    assert "Camera updated" in messages
    assert "Camera profile created" in messages
    assert "Camera profile updated" in messages
    assert "remote-secret-value" not in logs.text
    assert "profile-secret-value" not in logs.text

    settings_log = next(row for row in rows if row["message"] == "Settings updated")
    assert settings_log["context"]["settings_keys"] == ["observatory", "remote_upload"]
    schedule_log = next(row for row in rows if row["message"] == "Schedule updated")
    assert "interval_seconds" in schedule_log["context"]["changed_fields"]
    profile_log = next(row for row in rows if row["message"] == "Camera profile created")
    assert profile_log["context"]["settings_keys"] == ["api_key", "exposure_ms"]


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
            return Result(
                "Id=skyweaver-capture.service\n"
                "ActiveState=active\n"
                "MainPID=123\n"
                "Result=success\n"
                "NRestarts=0\n"
                "ActiveEnterTimestamp=Wed 2026-06-24 05:00:00 UTC\n"
            )
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
    assert data["failure_analysis"]["severity"] == "ok"
    assert data["unit_history"]["restarts"] == 0
    assert data["unit_history"]["recent_events"] == [{"label": "Entered active", "value": "Wed 2026-06-24 05:00:00 UTC"}]
    assert calls[0] == ["systemctl", "show", "skyweaver-capture.service", "--no-pager", "--property=Id,Description,LoadState,ActiveState,SubState,UnitFileState,MainPID,ExecMainStatus,ExecMainCode,ExecMainStartTimestamp,ExecMainExitTimestamp,Result,Restart,NRestarts,ActiveEnterTimestamp,InactiveEnterTimestamp,StateChangeTimestamp,FragmentPath,DropInPaths"]
    assert calls[1] == ["journalctl", "-u", "skyweaver-capture.service", "-n", "80", "--no-pager", "--output=short-iso"]
    assert client.get("/api/v1/system/services/not-skyweaver", headers={"Authorization": f"Bearer {token}"}).status_code == 404


def test_system_service_detail_reports_failure_analysis(tmp_path, monkeypatch):
    from skyweaver.api import routes

    client = make_client(tmp_path)
    token = login(client)

    class Result:
        def __init__(self, stdout: str):
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def fake_run(command, **_kwargs):
        if "show" in command:
            return Result(
                "Id=skyweaver-capture.service\n"
                "ActiveState=failed\n"
                "Result=exit-code\n"
                "ExecMainStatus=1\n"
                "NRestarts=3\n"
                "ExecMainExitTimestamp=Wed 2026-06-24 05:01:00 UTC\n"
            )
        return Result("2026-06-24T05:01:00 skyweaver-capture Permission denied opening /dev/media0\n")

    monkeypatch.setattr(routes, "systemctl_command", lambda: ["systemctl"])
    monkeypatch.setattr(routes.shutil, "which", lambda name: "journalctl" if name == "journalctl" else None)
    monkeypatch.setattr(routes.subprocess, "run", fake_run)

    res = client.get("/api/v1/system/services/skyweaver-capture", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["failure_analysis"]["severity"] == "error"
    assert any("ActiveState=failed" in item["message"] for item in data["failure_analysis"]["findings"])
    assert any("service user groups" in action for action in data["failure_analysis"]["suggested_actions"])
    assert data["unit_history"]["restarts"] == 3
    assert data["unit_history"]["exec_main_status"] == "1"


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
