import asyncio
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil
from PIL import Image, ImageStat

from ..camera.base import CaptureRequest
from ..camera.registry import get_adapter
from ..config import get_settings
from ..db import event, json_dumps, json_loads, log, new_id, now_iso, row_to_dict, session
from .schedule import should_capture_now


@dataclass
class CaptureCommand:
    camera_id: str | None = None
    exposure_ms: float = 1000
    gain: float = 1.0
    width: int | None = 1280
    height: int | None = 960
    format: str = "jpg"
    mode: str = "manual"
    settings: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "CaptureCommand":
        return cls(
            camera_id=payload.get("camera_id"),
            exposure_ms=float(payload.get("exposure_ms", 1000)),
            gain=float(payload.get("gain", 1.0)),
            width=payload.get("width", 1280),
            height=payload.get("height", 960),
            format=payload.get("format", "jpg"),
            mode=payload.get("mode", "manual"),
            settings=payload.get("settings", {}) or {},
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "exposure_ms": self.exposure_ms,
            "gain": self.gain,
            "width": self.width,
            "height": self.height,
            "format": self.format,
            "mode": self.mode,
            "settings": self.settings,
        }


def decode_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for key in ["capabilities", "settings", "metadata", "context", "request", "result", "input", "output", "payload", "value", "scopes"]:
        if key in out and isinstance(out[key], str):
            out[key] = json_loads(out[key], out[key])
    for key, value in list(out.items()):
        if isinstance(value, int) and key in {"enabled", "is_primary", "bad_image", "dark_frame_applied", "overlay_applied", "trusted"}:
            out[key] = bool(value)
    return out


def all_rows(conn, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [decode_row(row_to_dict(row)) for row in conn.execute(sql, params).fetchall()]


def get_primary_camera(conn, camera_id: str | None = None) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM cameras WHERE id=?", (camera_id,)).fetchone() if camera_id else conn.execute("SELECT * FROM cameras WHERE is_primary=1 LIMIT 1").fetchone()
    if not row:
        raise LookupError("Camera not found")
    return decode_row(row_to_dict(row))


def create_capture_job(conn, job_type: str, request: dict[str, Any]) -> str:
    job_id = new_id()
    conn.execute(
        "INSERT INTO capture_jobs (id, type, status, request, created_at) VALUES (?, ?, 'pending', ?, ?)",
        (job_id, job_type, json_dumps(request), now_iso()),
    )
    return job_id


def enqueue_capture(command: CaptureCommand, job_type: str = "single") -> dict[str, Any]:
    with session() as conn:
        job_id = create_capture_job(conn, job_type, command.as_dict())
        event(conn, "capture_queued", {"job_id": job_id, "type": job_type})
    return {"id": job_id, "status": "pending", "type": job_type}


def claim_next_capture_job(job_types: tuple[str, ...] = ("single", "scheduled", "sequence")) -> dict[str, Any] | None:
    placeholders = ",".join("?" for _ in job_types)
    with session() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            f"SELECT * FROM capture_jobs WHERE status='pending' AND type IN ({placeholders}) ORDER BY created_at LIMIT 1",
            job_types,
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE capture_jobs SET status='claimed', progress=0.02 WHERE id=? AND status='pending'", (row["id"],))
        conn.execute(
            "UPDATE capture_state SET daemon_last_claimed_job_id=?, daemon_last_claimed_job_type=?, daemon_last_claimed_at=?, updated_at=? WHERE id=1",
            (row["id"], row["type"], now_iso(), now_iso()),
        )
        event(conn, "capture_job_claimed", {"job_id": row["id"], "type": row["type"]})
        return decode_row(row_to_dict(row))


async def execute_capture_job(job: dict[str, Any]) -> dict[str, Any]:
    if job["type"] == "sequence":
        return await execute_sequence_job(job)
    return await execute_capture(CaptureCommand.from_mapping(job["request"]), job["type"], job_id=job["id"])


async def execute_sequence_job(job: dict[str, Any]) -> dict[str, Any]:
    request = job["request"]
    count = max(1, min(100, int(request.get("count", request.get("frames", 1)))))
    delay_seconds = max(0.0, float(request.get("delay_seconds", request.get("interval_seconds", 0))))
    capture_payload = request.get("capture") if isinstance(request.get("capture"), dict) else request
    command = CaptureCommand.from_mapping({**capture_payload, "mode": capture_payload.get("mode", "sequence")})
    image_ids: list[str] = []

    with session() as conn:
        conn.execute("UPDATE capture_jobs SET status='running', progress=0.05, started_at=? WHERE id=?", (now_iso(), job["id"]))

    try:
        for index in range(count):
            if not capture_is_running():
                break
            result = await execute_capture(command, "sequence_item")
            image_ids.append(result["image"]["id"])
            with session() as conn:
                conn.execute("UPDATE capture_jobs SET progress=? WHERE id=?", (len(image_ids) / count, job["id"]))
            if index < count - 1 and delay_seconds:
                await asyncio.sleep(delay_seconds)

        status = "completed" if len(image_ids) == count else "stopped"
        payload = {"image_ids": image_ids, "requested_count": count, "completed_count": len(image_ids)}
        with session() as conn:
            conn.execute("UPDATE capture_jobs SET status=?, progress=?, result=?, completed_at=? WHERE id=?", (status, len(image_ids) / count, json_dumps(payload), now_iso(), job["id"]))
            event(conn, "capture_sequence_completed", {"job_id": job["id"], **payload})
        return {"job_id": job["id"], **payload}
    except Exception as exc:
        with session() as conn:
            conn.execute("UPDATE capture_jobs SET status='failed', error=?, completed_at=? WHERE id=?", (str(exc), now_iso(), job["id"]))
            event(conn, "camera_error", {"job_id": job["id"], "error": str(exc)})
        raise


async def execute_capture(command: CaptureCommand, job_type: str = "manual", job_id: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    with session() as conn:
        cam = get_primary_camera(conn, command.camera_id)
        if job_id is None:
            job_id = create_capture_job(conn, job_type, command.as_dict())
        conn.execute("UPDATE capture_jobs SET status='running', progress=0.1, started_at=? WHERE id=?", (now_iso(), job_id))

    captured_at = datetime.now(UTC)
    day_key = captured_at.strftime("%Y%m%d")
    image_id = new_id()
    output = settings.image_dir / day_key / f"{captured_at.strftime('%H%M%S')}_{image_id[:8]}.{command.format.lower()}"
    adapter = get_adapter(cam["adapter"])

    try:
        result = await adapter.capture(
            CaptureRequest(
                output_path=output,
                exposure_ms=command.exposure_ms,
                gain=command.gain,
                width=command.width,
                height=command.height,
                image_format=command.format,
                mode=command.mode,
                settings=command.settings,
            )
        )
        metadata = {
            "id": image_id,
            "captured_at": captured_at.isoformat(),
            "camera": {"id": cam["id"], "adapter": cam["adapter"], "model": cam.get("model")},
            "settings": {"exposure_ms": command.exposure_ms, "gain": command.gain, "format": command.format},
            "environment": {"sensor_temperature_c": result.temperature_c, "system_temperature_c": read_pi_temp()},
            "analysis": analyze_image(result.file_path),
            **result.metadata,
        }
        sidecar = Path(str(result.file_path) + ".json")
        sidecar.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        thumb = make_thumbnail(result.file_path, settings.thumbnail_dir / day_key / result.file_path.name)

        with session() as conn:
            conn.execute(
                """INSERT INTO images
                   (id, camera_id, captured_at, day_key, mode, file_path, public_url, thumbnail_path, format, width, height,
                    size_bytes, exposure_ms, gain, temperature_c, mean_brightness, star_count, cloud_score, bad_image, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    image_id,
                    cam["id"],
                    captured_at.isoformat(),
                    day_key,
                    command.mode,
                    str(result.file_path),
                    f"/api/v1/images/{image_id}/download",
                    str(thumb) if thumb else None,
                    result.format,
                    result.width,
                    result.height,
                    result.size_bytes,
                    result.exposure_ms,
                    result.gain,
                    result.temperature_c,
                    metadata["analysis"]["mean_brightness"],
                    metadata["analysis"]["star_count"],
                    metadata["analysis"]["cloud_score"],
                    int(metadata["analysis"]["bad_image"]),
                    json_dumps(metadata),
                    now_iso(),
                ),
            )
            conn.execute(
                "UPDATE capture_state SET last_image_id=?, active_camera_id=?, daemon_last_success_at=?, last_error=NULL, updated_at=? WHERE id=1",
                (image_id, cam["id"], now_iso(), now_iso()),
            )
            conn.execute("UPDATE capture_jobs SET status='completed', progress=1, result=?, completed_at=? WHERE id=?", (json_dumps({"image_id": image_id}), now_iso(), job_id))
            event(conn, "new_image", {"image_id": image_id, "path": str(result.file_path)})

        return {"job_id": job_id, "image": {**metadata, "file_path": str(result.file_path), "thumbnail_path": str(thumb) if thumb else None}}
    except Exception as exc:
        with session() as conn:
            conn.execute("UPDATE capture_state SET status='error', last_error=?, updated_at=? WHERE id=1", (str(exc), now_iso()))
            conn.execute("UPDATE capture_jobs SET status='failed', error=?, completed_at=? WHERE id=?", (str(exc), now_iso(), job_id))
            log(conn, "error", "capture", "Capture failed", {"error": str(exc), "camera_id": cam["id"]})
            event(conn, "camera_error", {"error": str(exc), "camera_id": cam["id"]})
        raise


def schedule_command(camera_id: str | None = None) -> CaptureCommand:
    with session() as conn:
        camera = get_primary_camera(conn, camera_id)
        profile = conn.execute(
            "SELECT * FROM camera_profiles WHERE camera_id=? AND mode='nighttime' ORDER BY updated_at DESC LIMIT 1",
            (camera["id"],),
        ).fetchone()
    settings = json_loads(profile["settings"], {}) if profile else {}
    return CaptureCommand(
        camera_id=camera["id"],
        exposure_ms=float(settings.get("manual_exposure_ms", 1000)),
        gain=float(settings.get("gain", 1.0)),
        width=settings.get("width", 1280),
        height=settings.get("height", 960),
        format=settings.get("format", "jpg"),
        mode="night",
        settings=settings,
    )


def capture_interval_seconds() -> int:
    with session() as conn:
        row = conn.execute("SELECT interval_seconds FROM capture_schedule LIMIT 1").fetchone()
    if not row:
        return 30
    return max(1, int(row["interval_seconds"]))


def current_schedule() -> dict[str, Any]:
    with session() as conn:
        row = conn.execute("SELECT * FROM capture_schedule LIMIT 1").fetchone()
    return decode_row(row_to_dict(row)) or {}


def schedule_allows_capture() -> bool:
    schedule = current_schedule()
    return should_capture_now(schedule)


def capture_is_running() -> bool:
    with session() as conn:
        row = conn.execute("SELECT status FROM capture_state WHERE id=1").fetchone()
    return bool(row and row["status"] == "running")


def update_daemon_heartbeat(pid: int | None = None) -> None:
    with session() as conn:
        conn.execute(
            "UPDATE capture_state SET daemon_heartbeat_at=?, daemon_pid=?, updated_at=? WHERE id=1",
            (now_iso(), pid if pid is not None else os.getpid(), now_iso()),
        )


def analyze_image(path: Path) -> dict[str, Any]:
    with Image.open(path) as img:
        gray = img.convert("L")
        mean = ImageStat.Stat(gray).mean[0] / 255
    return {"mean_brightness": round(mean, 4), "star_count": None, "cloud_score": None, "bad_image": mean < 0.01 or mean > 0.98}


def make_thumbnail(source: Path, target: Path) -> Path | None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(source) as img:
            img.thumbnail((360, 360))
            img.save(target)
        return target
    except Exception:
        return None


def read_pi_temp() -> float | None:
    path = Path("/sys/class/thermal/thermal_zone0/temp")
    if path.exists():
        try:
            return round(int(path.read_text().strip()) / 1000, 1)
        except ValueError:
            return None
    return None


def system_metrics() -> dict[str, Any]:
    disk = shutil.disk_usage(get_settings().data_dir)
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": round((disk.used / disk.total) * 100, 2),
        "disk_free_gb": round(disk.free / 1024 / 1024 / 1024, 2),
        "temperature_c": read_pi_temp(),
        "uptime_seconds": int(datetime.now().timestamp() - psutil.boot_time()),
    }


def count_files(root: Path, patterns: list[str]) -> int:
    if not root.exists():
        return 0
    return sum(1 for pattern in patterns for _ in root.rglob(pattern))
