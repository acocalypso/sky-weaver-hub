from pathlib import Path
import asyncio
from datetime import UTC, datetime, timedelta

from test_api import login, make_client, run_queued_test_capture


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
    restarted_daemon = CaptureDaemon()
    assert asyncio.run(restarted_daemon.run_once()) is False

    images = client.get("/api/v1/images", headers={"Authorization": f"Bearer {token}"}).json()["data"]
    assert len(images) == 1


def test_schedule_preview_reports_persisted_next_capture_due(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.put(
        "/api/v1/schedule",
        headers=headers,
        json={
            "enabled": True,
            "start_mode": "fixed",
            "end_mode": "fixed",
            "fixed_start_time": "00:00",
            "fixed_end_time": "23:59",
            "sun_angle": -6,
            "timezone": "UTC",
            "latitude": 0,
            "longitude": 0,
            "interval_seconds": 60,
            "exposure_ramping_enabled": False,
        },
    ).status_code == 200
    assert client.post("/api/v1/capture/start", headers=headers).status_code == 200

    from skyweaver.capture_daemon import CaptureDaemon

    daemon = CaptureDaemon()
    assert asyncio.run(daemon.run_once(True)) is True

    preview = client.post("/api/v1/schedule/preview-tonight", headers=headers, json={})
    assert preview.status_code == 200, preview.text
    data = preview.json()["data"]
    assert data["capture_mode"] == "night"
    assert data["interval_seconds"] >= 1
    assert data["last_scheduled_capture_at"]
    assert data["next_capture_due_at"]
    assert data["seconds_until_due"] >= 0
    assert data["capture_due"] is False


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


def test_daemon_day_profile_can_update_latest_without_saving(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    from skyweaver.db import json_dumps, json_loads, session

    with session() as conn:
        row = conn.execute("SELECT id, settings FROM camera_profiles WHERE mode='daytime' LIMIT 1").fetchone()
        settings = json_loads(row["settings"], {})
        settings.update({"capture_enabled": True, "save_enabled": False, "interval_seconds": 1})
        conn.execute("UPDATE camera_profiles SET settings=? WHERE id=?", (json_dumps(settings), row["id"]))

    assert client.post("/api/v1/capture/start", headers=headers).status_code == 200

    from skyweaver.capture_daemon import CaptureDaemon

    daemon = CaptureDaemon()
    assert asyncio.run(daemon.run_once()) is True

    images = client.get("/api/v1/images", headers=headers).json()["data"]
    assert images == []

    jobs = client.get("/api/v1/capture/jobs", headers=headers).json()["data"]
    assert jobs[0]["status"] == "completed"
    assert jobs[0]["result"]["unsaved_latest"] is True

    public_latest = client.get("/api/v1/public/latest")
    assert public_latest.status_code == 200
    latest_data = public_latest.json()["data"]
    assert latest_data["mode"] == "day"
    assert latest_data["download_url"] == "/api/v1/public/latest/download"
    assert client.get("/api/v1/public/latest/download").status_code == 200


def test_daemon_queues_end_of_night_products_once(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    from skyweaver.db import json_dumps, json_loads, session

    _queued, _job, image = run_queued_test_capture(client, headers, {"exposure_ms": 250, "gain": 1, "format": "jpg", "mode": "night"})
    day_key = image["day_key"]
    assert client.post("/api/v1/capture/start", headers=headers).status_code == 200

    with session() as conn:
        row = conn.execute("SELECT id, settings FROM camera_profiles WHERE mode='nighttime' LIMIT 1").fetchone()
        settings = json_loads(row["settings"], {})
        settings.update(
            {
                "save_enabled": True,
                "end_of_night_keogram": True,
                "end_of_night_startrail": True,
                "end_of_night_timelapse": False,
                "end_of_night_mini_timelapse": False,
            }
        )
        conn.execute("UPDATE camera_profiles SET settings=? WHERE id=?", (json_dumps(settings), row["id"]))

    from skyweaver.capture_daemon import CaptureDaemon
    from skyweaver.services.capture import set_scheduled_mode_state

    daemon = CaptureDaemon()
    set_scheduled_mode_state("night")
    assert asyncio.run(daemon.run_once()) is False

    jobs = client.get("/api/v1/processing/jobs", headers=headers).json()["data"]
    queued_types = {job["type"] for job in jobs}
    assert queued_types == {"keogram", "startrail"}
    assert all(job["input"]["day_key"] == day_key for job in jobs)

    set_scheduled_mode_state("night")
    daemon.last_scheduled_mode = None
    assert asyncio.run(daemon.run_once()) is False
    jobs_after = client.get("/api/v1/processing/jobs", headers=headers).json()["data"]
    assert len(jobs_after) == 2


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
    assert before["progress"] == 0

    from skyweaver.capture_daemon import CaptureDaemon

    daemon = CaptureDaemon()
    assert asyncio.run(daemon.run_once()) is True

    after = client.get(f"/api/v1/capture/jobs/{queued['id']}", headers=headers).json()["data"]
    assert after["status"] == "completed"
    assert after["progress"] == 1
    assert after["result"]["image_id"]

    status = client.get("/api/v1/status", headers=headers).json()["data"]["capture"]
    assert status["daemon_last_claimed_job_id"] == queued["id"]
    assert status["daemon_last_claimed_job_type"] == "single"
    assert status["daemon_last_claimed_at"]
    assert status["daemon_last_success_at"]

    images = client.get("/api/v1/images", headers=headers).json()["data"]
    assert len(images) == 1
    assert images[0]["mode"] == "manual"


def test_daemon_consumes_test_shot_while_capture_is_stopped(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    queued = client.post(
        "/api/v1/capture/test-shot",
        headers=headers,
        json={"exposure_ms": 250, "gain": 1, "mode": "manual"},
    ).json()["data"]
    assert queued["status"] == "pending"
    assert queued["type"] == "test"

    from skyweaver.capture_daemon import CaptureDaemon

    daemon = CaptureDaemon()
    assert asyncio.run(daemon.run_once()) is True

    after = client.get(f"/api/v1/capture/jobs/{queued['id']}", headers=headers).json()["data"]
    assert after["status"] == "completed"
    assert after["result"]["image_id"]

    status = client.get("/api/v1/status", headers=headers).json()["data"]["capture"]
    assert status["status"] == "idle"
    assert status["daemon_last_claimed_job_id"] == queued["id"]
    assert status["daemon_last_claimed_job_type"] == "test"


def test_pause_holds_queued_capture_until_resume(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/capture/start", headers=headers).status_code == 200
    assert client.post("/api/v1/capture/pause", headers=headers).status_code == 200

    queued = client.post(
        "/api/v1/capture/single",
        headers=headers,
        json={"exposure_ms": 250, "gain": 1, "mode": "manual"},
    ).json()["data"]

    from skyweaver.capture_daemon import CaptureDaemon

    daemon = CaptureDaemon()
    assert asyncio.run(daemon.run_once()) is False
    paused_job = client.get(f"/api/v1/capture/jobs/{queued['id']}", headers=headers).json()["data"]
    assert paused_job["status"] == "pending"
    assert client.get("/api/v1/images", headers=headers).json()["data"] == []

    assert client.post("/api/v1/capture/resume", headers=headers).status_code == 200
    assert asyncio.run(daemon.run_once()) is True
    completed_job = client.get(f"/api/v1/capture/jobs/{queued['id']}", headers=headers).json()["data"]
    assert completed_job["status"] == "completed"


def test_stop_cancels_pending_capture_jobs(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/capture/start", headers=headers).status_code == 200
    queued = client.post("/api/v1/capture/single", headers=headers, json={"mode": "manual"}).json()["data"]
    test_queued = client.post("/api/v1/capture/test-shot", headers=headers, json={"mode": "manual"}).json()["data"]

    stopped = client.post("/api/v1/capture/stop", headers=headers).json()["data"]
    assert stopped["status"] == "stopped"
    assert stopped["stop_mode"] == "graceful"
    assert stopped["canceled_jobs"] == 2
    assert stopped["in_progress_jobs"] == 0
    assert stopped["in_progress_job_ids"] == []
    assert stopped["adapter_cancel_mode"] == "best_effort"
    assert stopped["cancel_requested_jobs"] == 0
    assert stopped["cancel_requested_job_ids"] == []
    assert "safe hard-cancel support" in stopped["message"]

    after = client.get(f"/api/v1/capture/jobs/{queued['id']}", headers=headers).json()["data"]
    assert after["status"] == "canceled"
    assert after["error"] == "Canceled by operator stop"
    test_after = client.get(f"/api/v1/capture/jobs/{test_queued['id']}", headers=headers).json()["data"]
    assert test_after["status"] == "canceled"
    assert test_after["error"] == "Canceled by operator stop"


def test_stop_reports_running_capture_jobs(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/capture/start", headers=headers).status_code == 200
    queued = client.post("/api/v1/capture/single", headers=headers, json={"mode": "manual"}).json()["data"]

    from skyweaver.db import session

    with session() as conn:
        conn.execute(
            "UPDATE capture_jobs SET status='running', progress=0.4, started_at='2026-06-23T00:00:00+00:00' WHERE id=?",
            (queued["id"],),
        )

    stopped = client.post("/api/v1/capture/stop", headers=headers).json()["data"]
    assert stopped["status"] == "stopped"
    assert stopped["stop_mode"] == "graceful"
    assert stopped["canceled_jobs"] == 0
    assert stopped["in_progress_jobs"] == 1
    assert stopped["in_progress_job_ids"] == [queued["id"]]
    assert stopped["adapter_cancel_mode"] == "best_effort"
    assert stopped["cancel_requested_jobs"] == 1
    assert stopped["cancel_requested_job_ids"] == [queued["id"]]

    with session() as conn:
        job = conn.execute("SELECT cancel_requested_at, cancel_reason, cancel_mode FROM capture_jobs WHERE id=?", (queued["id"],)).fetchone()
    assert job["cancel_requested_at"]
    assert job["cancel_reason"] == "Operator stop"
    assert job["cancel_mode"] == "best_effort"


def test_hard_cancel_supported_adapter_stops_running_capture(tmp_path: Path, monkeypatch):
    client = make_client(tmp_path)
    assert client.get("/api/v1/health").status_code == 200

    from skyweaver.camera.base import CaptureCancelResult, CaptureCanceled, CaptureRequest
    from skyweaver.db import now_iso, session
    from skyweaver.services import capture as capture_service
    from skyweaver.services.capture import CaptureCommand, execute_capture

    class CancellableAdapter:
        supports_hard_cancel = True

        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.cancelled = asyncio.Event()
            self.job_id = None
            self.cancel_calls = []

        async def capture(self, request: CaptureRequest):
            self.job_id = request.job_id
            self.started.set()
            await self.cancelled.wait()
            raise CaptureCanceled("Capture canceled by operator stop")

        async def cancel_capture(self, job_id: str, reason: str = "operator stop") -> CaptureCancelResult:
            self.cancel_calls.append((job_id, reason))
            self.cancelled.set()
            return CaptureCancelResult(supported=True, canceled=True, method="test", message=reason)

    adapter = CancellableAdapter()
    monkeypatch.setattr(capture_service, "get_adapter", lambda _adapter: adapter)

    async def run_and_stop():
        task = asyncio.create_task(execute_capture(CaptureCommand(exposure_ms=5000, gain=1, format="jpg", mode="manual"), job_type="single"))
        await asyncio.wait_for(adapter.started.wait(), timeout=2)
        with session() as conn:
            conn.execute("UPDATE capture_state SET status='stopped', current_mode='manual', updated_at=? WHERE id=1", (now_iso(),))
            conn.execute(
                "UPDATE capture_jobs SET cancel_requested_at=?, cancel_reason='Operator stop', cancel_mode='best_effort' WHERE id=?",
                (now_iso(), adapter.job_id),
            )
        return await asyncio.wait_for(task, timeout=2)

    result = asyncio.run(run_and_stop())

    assert result["canceled"] is True
    assert adapter.cancel_calls == [(adapter.job_id, "Operator stop")]
    with session() as conn:
        job = conn.execute("SELECT * FROM capture_jobs WHERE id=?", (adapter.job_id,)).fetchone()
        image_count = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
    assert job["status"] == "canceled"
    assert "hard_cancel" in job["result"]
    assert image_count == 0


def test_running_capture_finishes_as_stopped_after_stop_request(tmp_path: Path, monkeypatch):
    client = make_client(tmp_path)
    assert client.get("/api/v1/health").status_code == 200

    from PIL import Image

    from skyweaver.camera.base import CaptureRequest, CaptureResult
    from skyweaver.db import now_iso, session
    from skyweaver.services import capture as capture_service
    from skyweaver.services.capture import CaptureCommand, execute_capture

    class SlowAdapter:
        async def capture(self, request: CaptureRequest) -> CaptureResult:
            with session() as conn:
                conn.execute("UPDATE capture_state SET status='stopped', current_mode='manual', updated_at=? WHERE id=1", (now_iso(),))
            request.output_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (32, 32), color=(12, 18, 24)).save(request.output_path)
            return CaptureResult(file_path=request.output_path, format="jpg", width=32, height=32, size_bytes=request.output_path.stat().st_size)

    monkeypatch.setattr(capture_service, "get_adapter", lambda _adapter: SlowAdapter())

    result = asyncio.run(execute_capture(CaptureCommand(exposure_ms=250, gain=1, format="jpg", mode="manual"), job_type="single"))

    with session() as conn:
        job = conn.execute("SELECT * FROM capture_jobs WHERE id=?", (result["job_id"],)).fetchone()

    assert job["status"] == "stopped"
    assert "completed_after_stop" in job["result"]
    assert "stop_mode" in job["result"]


def test_execute_capture_passes_configured_camera_device_id(tmp_path: Path, monkeypatch):
    client = make_client(tmp_path)
    assert client.get("/api/v1/health").status_code == 200

    from PIL import Image

    from skyweaver.camera.base import CaptureRequest, CaptureResult
    from skyweaver.db import session
    from skyweaver.services import capture as capture_service
    from skyweaver.services.capture import CaptureCommand, execute_capture

    class DeviceAwareAdapter:
        def __init__(self) -> None:
            self.request_settings = None

        async def capture(self, request: CaptureRequest) -> CaptureResult:
            self.request_settings = dict(request.settings)
            request.output_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (16, 16), color=(20, 30, 40)).save(request.output_path)
            return CaptureResult(file_path=request.output_path, format="jpg", width=16, height=16, size_bytes=request.output_path.stat().st_size)

    adapter = DeviceAwareAdapter()
    monkeypatch.setattr(capture_service, "get_adapter", lambda _adapter: adapter)
    with session() as conn:
        conn.execute("UPDATE cameras SET adapter='zwo', device_id='zwo://2' WHERE is_primary=1")

    asyncio.run(execute_capture(CaptureCommand(exposure_ms=250, gain=1, format="jpg", mode="manual"), job_type="single"))

    assert adapter.request_settings is not None
    assert adapter.request_settings["device_id"] == "zwo://2"


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
    assert queued["type"] == "sequence"
    assert queued["progress"] == 0

    from skyweaver.capture_daemon import CaptureDaemon

    daemon = CaptureDaemon()
    assert asyncio.run(daemon.run_once()) is True

    after = client.get(f"/api/v1/capture/jobs/{queued['id']}", headers=headers).json()["data"]
    assert after["status"] == "completed"
    assert after["progress"] == 1
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


def test_schedule_preview_supports_named_twilight_window(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    preview = client.post(
        "/api/v1/schedule/preview-tonight",
        headers=headers,
        json={
            "enabled": True,
            "start_mode": "nautical_dusk",
            "end_mode": "sunrise",
            "timezone": "Europe/Berlin",
            "latitude": 49.1012,
            "longitude": 10.1210,
            "now": "2026-06-30T01:00:00+02:00",
        },
    )

    assert preview.status_code == 200, preview.text
    data = preview.json()["data"]
    assert data["active"] is True
    assert data["window_start"].startswith("2026-06-29T")
    assert data["window_end"].startswith("2026-06-30T")
    assert data["timezone"] == "Europe/Berlin"


def test_schedule_persists_independent_sun_angles(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}

    saved = client.put(
        "/api/v1/schedule",
        headers=headers,
        json={
            "enabled": True,
            "start_mode": "sun_angle",
            "end_mode": "sun_angle",
            "sun_angle": -6,
            "start_sun_angle": -8,
            "end_sun_angle": -2,
            "timezone": "Europe/Berlin",
            "latitude": 49.1012,
            "longitude": 10.1210,
            "interval_seconds": 30,
            "exposure_ramping_enabled": False,
        },
    )

    assert saved.status_code == 200, saved.text
    schedule = client.get("/api/v1/schedule", headers=headers).json()["data"]
    assert schedule["start_sun_angle"] == -8
    assert schedule["end_sun_angle"] == -2


def test_scheduled_capture_due_uses_previous_start_time(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.put(
        "/api/v1/schedule",
        headers=headers,
        json={
            "enabled": True,
            "start_mode": "fixed",
            "end_mode": "fixed",
            "fixed_start_time": "00:00",
            "fixed_end_time": "23:59",
            "sun_angle": -6,
            "timezone": "UTC",
            "latitude": 0,
            "longitude": 0,
            "interval_seconds": 30,
            "exposure_ramping_enabled": False,
        },
    ).status_code == 200

    from skyweaver.db import json_dumps, new_id, session
    from skyweaver.services.capture import scheduled_capture_timing

    now = datetime(2026, 6, 30, 7, 13, 39, tzinfo=UTC)
    with session() as conn:
        camera = conn.execute("SELECT id FROM cameras WHERE is_primary=1 LIMIT 1").fetchone()
        profile = conn.execute("SELECT id, settings FROM camera_profiles WHERE camera_id=? AND mode='nighttime'", (camera["id"],)).fetchone()
        settings = {"capture_enabled": True, "save_enabled": True, "interval_seconds": 30}
        conn.execute("UPDATE camera_profiles SET settings=? WHERE id=?", (json_dumps(settings), profile["id"]))
        conn.execute(
            """INSERT INTO capture_jobs (id, type, status, request, result, progress, created_at, completed_at)
               VALUES (?, 'scheduled', 'completed', ?, ?, 1, ?, ?)""",
            (
                new_id(),
                json_dumps({"mode": "night", "camera_id": camera["id"]}),
                json_dumps({"image_id": new_id()}),
                (now - timedelta(seconds=101)).isoformat(),
                now.isoformat(),
            ),
        )

    timing = scheduled_capture_timing("night", now, camera_id=camera["id"])
    assert timing["capture_due"] is True
    assert timing["last_scheduled_capture_at"] == now.isoformat()
    assert timing["last_scheduled_capture_started_at"] == (now - timedelta(seconds=101)).isoformat()


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
    assert "last_claimed_job_id" in capture
    assert "last_success_at" in capture


def test_daemon_lock_recovers_stale_pid_file(tmp_path: Path):
    client = make_client(tmp_path)
    assert client.get("/api/v1/health").status_code == 200

    from skyweaver.config import get_settings
    from skyweaver.capture_daemon import daemon_lock

    lock_path = get_settings().data_dir / "capture-daemon.lock"
    lock_path.write_text("999999", encoding="ascii")

    with daemon_lock():
        assert lock_path.read_text(encoding="ascii") != "999999"

    assert not lock_path.exists()


def test_mock_overnight_simulation_updates_latest_gallery_and_recovers(tmp_path: Path):
    client = make_client(tmp_path)
    token = login(client)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.put(
        "/api/v1/schedule",
        headers=headers,
        json={
            "enabled": True,
            "start_mode": "manual",
            "end_mode": "manual",
            "sun_angle": -6,
            "timezone": "UTC",
            "latitude": 0,
            "longitude": 0,
            "interval_seconds": 1,
            "exposure_ramping_enabled": False,
        },
    ).status_code == 200
    assert client.post("/api/v1/capture/start", headers=headers).status_code == 200

    from skyweaver.capture_daemon import CaptureDaemon
    from skyweaver.db import session
    from skyweaver.services.recovery import recover_capture_jobs

    daemon = CaptureDaemon()
    for _ in range(4):
        assert asyncio.run(daemon.run_once(True)) is True

    images = client.get("/api/v1/images?limit=10", headers=headers).json()["data"]
    assert len(images) == 4
    assert [image["captured_at"] for image in images] == sorted((image["captured_at"] for image in images), reverse=True)
    assert all(Path(image["file_path"]).exists() for image in images)
    assert all(Path(image["file_path"] + ".json").exists() for image in images)
    assert all(image["thumbnail_path"] and Path(image["thumbnail_path"]).exists() for image in images)

    latest = client.get("/api/v1/images/latest", headers=headers).json()["data"]
    assert latest["id"] == images[0]["id"]
    status = client.get("/api/v1/status", headers=headers).json()["data"]
    assert status["latest_image"]["id"] == latest["id"]
    assert status["capture"]["last_image_id"] == latest["id"]

    queued = client.post("/api/v1/capture/single", headers=headers, json={"mode": "manual", "exposure_ms": 250, "gain": 1}).json()["data"]
    with session() as conn:
        conn.execute(
            "UPDATE capture_jobs SET status='claimed', progress=0.02, started_at='2026-06-23T00:00:00+00:00' WHERE id=?",
            (queued["id"],),
        )

    recovered = recover_capture_jobs()
    assert recovered["requeued"] == 1
    assert asyncio.run(daemon.run_once()) is True
    recovered_job = client.get(f"/api/v1/capture/jobs/{queued['id']}", headers=headers).json()["data"]
    assert recovered_job["status"] == "completed"
    assert recovered_job["progress"] == 1

    after_recovery = client.get("/api/v1/images?limit=10", headers=headers).json()["data"]
    assert len(after_recovery) == 5
