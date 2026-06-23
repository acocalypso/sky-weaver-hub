from pathlib import Path
import asyncio

from test_api import login, make_client


def test_daemon_run_once_creates_scheduled_capture(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    assert client.post("/api/v1/capture/start", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    from skyweaver.capture_daemon import CaptureDaemon

    daemon = CaptureDaemon()
    captured = asyncio.run(daemon.run_once(True))
    assert captured is True

    images = client.get("/api/v1/images", headers={"Authorization": f"Bearer {token}"}).json()["data"]
    assert len(images) == 1
    assert images[0]["mode"] == "night"
    assert Path(images[0]["file_path"]).exists()


def test_daemon_respects_interval(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    assert client.put(
        "/api/v1/schedule",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "enabled": True,
            "start_mode": "manual",
            "end_mode": "manual",
            "sun_angle": -6,
            "timezone": "UTC",
            "latitude": 0,
            "longitude": 0,
            "interval_seconds": 60,
            "exposure_ramping_enabled": False,
        },
    ).status_code == 200
    assert client.post("/api/v1/capture/start", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    from skyweaver.capture_daemon import CaptureDaemon

    daemon = CaptureDaemon()
    assert asyncio.run(daemon.run_once(True)) is True
    assert asyncio.run(daemon.run_once()) is False

    images = client.get("/api/v1/images", headers={"Authorization": f"Bearer {token}"}).json()["data"]
    assert len(images) == 1


def test_daemon_skips_scheduled_capture_when_schedule_disabled(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/capture/start", headers=headers).status_code == 200

    from skyweaver.capture_daemon import CaptureDaemon

    daemon = CaptureDaemon()
    assert asyncio.run(daemon.run_once()) is False

    images = client.get("/api/v1/images", headers=headers).json()["data"]
    assert images == []


def test_daemon_consumes_queued_single_capture(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/capture/start", headers=headers).status_code == 200

    queued = client.post(
        "/api/v1/capture/single",
        headers=headers,
        json={"exposure_ms": 500, "gain": 2, "mode": "manual"},
    ).json()["data"]
    assert queued["status"] == "pending"

    before = client.get(f"/api/v1/capture/jobs/{queued['id']}", headers=headers).json()["data"]
    assert before["status"] == "pending"

    from skyweaver.capture_daemon import CaptureDaemon

    daemon = CaptureDaemon()
    assert asyncio.run(daemon.run_once()) is True

    after = client.get(f"/api/v1/capture/jobs/{queued['id']}", headers=headers).json()["data"]
    assert after["status"] == "completed"
    assert after["result"]["image_id"]

    images = client.get("/api/v1/images", headers=headers).json()["data"]
    assert len(images) == 1
    assert images[0]["mode"] == "manual"


def test_daemon_consumes_queued_sequence_capture(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/capture/start", headers=headers).status_code == 200

    queued = client.post(
        "/api/v1/capture/sequence",
        headers=headers,
        json={
            "count": 3,
            "delay_seconds": 0,
            "capture": {"exposure_ms": 250, "gain": 1.5, "mode": "sequence"},
        },
    ).json()["data"]
    assert queued["status"] == "pending"

    from skyweaver.capture_daemon import CaptureDaemon

    daemon = CaptureDaemon()
    assert asyncio.run(daemon.run_once()) is True

    after = client.get(f"/api/v1/capture/jobs/{queued['id']}", headers=headers).json()["data"]
    assert after["status"] == "completed"
    assert after["result"]["requested_count"] == 3
    assert after["result"]["completed_count"] == 3
    assert len(after["result"]["image_ids"]) == 3

    images = client.get("/api/v1/images?mode=sequence", headers=headers).json()["data"]
    assert len(images) == 3


def test_schedule_preview_reports_active_fixed_window(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    preview = client.post(
        "/api/v1/schedule/preview-tonight",
        headers=headers,
        json={
            "enabled": True,
            "start_mode": "fixed",
            "end_mode": "fixed",
            "fixed_start_time": "18:00",
            "fixed_end_time": "06:00",
            "timezone": "UTC",
            "now": "2026-06-23T23:00:00+00:00",
        },
    ).json()["data"]

    assert preview["active"] is True
    assert preview["next_state"] == "inactive"
    assert preview["window_start"].startswith("2026-06-23T18:00:00")
    assert preview["window_end"].startswith("2026-06-24T06:00:00")


def test_daemon_heartbeat_is_reported_by_services(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    from skyweaver.capture_daemon import CaptureDaemon

    daemon = CaptureDaemon()
    assert asyncio.run(daemon.run_once()) is False

    services = client.get("/api/v1/system/services", headers=headers).json()["data"]
    capture = next(item for item in services if item["name"] == "skyweaver-capture")
    assert capture["status"] == "running"
    assert capture["heartbeat_at"]
    assert capture["pid"]
