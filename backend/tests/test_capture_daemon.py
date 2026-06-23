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
