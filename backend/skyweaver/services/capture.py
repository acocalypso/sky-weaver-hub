import asyncio
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psutil
from PIL import ExifTags, Image, ImageStat

from ..camera.base import CameraAdapter, CaptureCancelResult, CaptureCanceled, CaptureRequest, CaptureResult
from ..camera.registry import get_adapter
from ..config import get_settings
from ..db import event, json_dumps, json_loads, log, new_id, now_iso, row_to_dict, session
from .overlay import apply_overlay, overlay_enabled, overlay_settings
from .schedule import should_capture_now


CAPTURE_MODE_TO_PROFILE = {"day": "daytime", "night": "nighttime"}


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


def capture_cancel_request(job_id: str) -> dict[str, Any] | None:
    with session() as conn:
        row = conn.execute(
            "SELECT cancel_requested_at, cancel_reason, cancel_mode FROM capture_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
    data = row_to_dict(row)
    if not data or not data.get("cancel_requested_at"):
        return None
    return data


async def capture_with_cancel(adapter: CameraAdapter, request: CaptureRequest, job_id: str) -> tuple[CaptureResult, CaptureCancelResult | None]:
    task = asyncio.create_task(adapter.capture(request))
    cancel_attempted = False
    cancel_result: CaptureCancelResult | None = None
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=0.2)
            if task.done() or cancel_attempted:
                continue
            cancel_request = capture_cancel_request(job_id)
            if cancel_request and adapter.supports_hard_cancel:
                cancel_attempted = True
                cancel_result = await adapter.cancel_capture(job_id, cancel_request.get("cancel_reason") or "operator stop")
                if cancel_result.canceled:
                    event_payload = {
                        "job_id": job_id,
                        "method": cancel_result.method,
                        "message": cancel_result.message,
                    }
                    with session() as conn:
                        event(conn, "capture_hard_cancel_requested", event_payload)
        result = await task
        if cancel_result and cancel_result.canceled:
            exc = CaptureCanceled("Capture canceled by operator stop")
            setattr(exc, "cancel_result", cancel_result)
            raise exc
        return result, cancel_result
    except CaptureCanceled as exc:
        setattr(exc, "cancel_result", getattr(exc, "cancel_result", cancel_result))
        raise


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


def public_latest_payload(image: dict[str, Any], latest_image: Path | None = None, latest_thumbnail: Path | None = None) -> dict[str, Any]:
    payload = {
        "id": image["id"],
        "captured_at": image["captured_at"],
        "day_key": image["day_key"],
        "mode": image["mode"],
        "format": image["format"],
        "width": image["width"],
        "height": image["height"],
        "size_bytes": image["size_bytes"],
        "exposure_ms": image.get("exposure_ms"),
        "gain": image.get("gain"),
        "camera_id": image.get("camera_id"),
        "download_url": "/api/v1/public/latest/download",
        "metadata_url": "/api/v1/public/latest",
        "thumbnail_url": "/api/v1/public/latest/thumbnail" if latest_thumbnail else None,
    }
    if latest_image:
        payload["latest_file"] = latest_image.name
    if latest_thumbnail:
        payload["latest_thumbnail_file"] = latest_thumbnail.name
    return payload


def copy_atomic(source: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    shutil.copy2(source, tmp)
    os.replace(tmp, target)
    return target


def remove_stale_latest_files(directory: Path, keep: set[Path]) -> None:
    for pattern in ("latest.*", "latest-thumbnail.*"):
        for path in directory.glob(pattern):
            if path not in keep and not path.name.startswith("."):
                path.unlink(missing_ok=True)


def publish_latest_image(image: dict[str, Any], metadata: dict[str, Any], thumbnail_path: Path | None) -> dict[str, Any]:
    settings = get_settings()
    latest_image = settings.latest_dir / f"latest.{image['format'].lower()}"
    latest_thumbnail = settings.latest_dir / f"latest-thumbnail{thumbnail_path.suffix.lower()}" if thumbnail_path else None
    remove_stale_latest_files(settings.latest_dir, {latest_image, *(set([latest_thumbnail]) if latest_thumbnail else set())})
    copy_atomic(Path(image["file_path"]), latest_image)
    if latest_thumbnail and thumbnail_path:
        copy_atomic(thumbnail_path, latest_thumbnail)
    payload = public_latest_payload(image, latest_image, latest_thumbnail)
    (settings.latest_dir / "latest.json").write_text(json.dumps({**payload, "metadata": metadata}, indent=2), encoding="utf-8")
    return payload


def read_latest_payload() -> dict[str, Any] | None:
    path = get_settings().latest_dir / "latest.json"
    if not path.exists():
        return None
    try:
        return json_loads(path.read_text(encoding="utf-8"), None)
    except (OSError, json.JSONDecodeError):
        return None


def _storage_delete_roots() -> list[Path]:
    settings = get_settings()
    return [
        settings.data_dir,
        settings.image_dir,
        settings.thumbnail_dir,
        settings.latest_dir,
    ]


def _path_within_roots(path: Path, roots: list[Path]) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def _delete_storage_file(path: Path, roots: list[Path]) -> dict[str, Any]:
    result = {"path": str(path), "status": "missing"}
    if not _path_within_roots(path, roots):
        result["status"] = "skipped"
        result["reason"] = "outside_storage_roots"
        return result
    if not path.exists():
        return result
    if not path.is_file():
        result["status"] = "skipped"
        result["reason"] = "not_a_file"
        return result
    path.unlink()
    result["status"] = "deleted"
    return result


def image_storage_artifacts(image: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for key in ("file_path", "thumbnail_path"):
        value = image.get(key)
        if value:
            paths.append(Path(str(value)))
    if image.get("file_path"):
        paths.append(Path(str(image["file_path"]) + ".json"))
    return paths


def latest_artifacts_for_image(image_id: str) -> list[Path]:
    settings = get_settings()
    payload = read_latest_payload()
    if not payload or payload.get("id") != image_id:
        return []
    paths = [settings.latest_dir / "latest.json"]
    for key in ("latest_file", "latest_thumbnail_file"):
        name = payload.get(key)
        if name:
            paths.append(settings.latest_dir / Path(str(name)).name)
    return paths


def delete_image_files(image: dict[str, Any]) -> dict[str, Any]:
    return delete_storage_paths([*image_storage_artifacts(image), *latest_artifacts_for_image(str(image["id"]))])


def delete_storage_paths(paths: list[Path]) -> dict[str, Any]:
    roots = _storage_delete_roots()
    seen: set[Path] = set()
    files: list[dict[str, Any]] = []
    for path in paths:
        marker = path.absolute()
        if marker in seen:
            continue
        seen.add(marker)
        files.append(_delete_storage_file(path, roots))
    return {
        "deleted_files": [item["path"] for item in files if item["status"] == "deleted"],
        "missing_files": [item["path"] for item in files if item["status"] == "missing"],
        "skipped_files": [item for item in files if item["status"] == "skipped"],
    }


def configured_image_retention_days(conn) -> int:
    row = conn.execute("SELECT value FROM system_settings WHERE key='storage'").fetchone()
    if not row:
        return 30
    value = json_loads(row["value"], {})
    if not isinstance(value, dict):
        return 30
    try:
        return max(0, int(value.get("retention_days", 30)))
    except (TypeError, ValueError):
        return 30


def cleanup_images_by_retention(conn, retention_days: int) -> dict[str, Any]:
    days = max(0, int(retention_days))
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = all_rows(conn, "SELECT * FROM images WHERE captured_at < ? ORDER BY captured_at", (cutoff.isoformat(),))
    deleted_ids: list[str] = []
    deleted_files: list[str] = []
    missing_files: list[str] = []
    skipped_files: list[dict[str, Any]] = []
    for image in rows:
        file_result = delete_image_files(image)
        conn.execute("DELETE FROM images WHERE id=?", (image["id"],))
        deleted_ids.append(image["id"])
        deleted_files.extend(file_result["deleted_files"])
        missing_files.extend(file_result["missing_files"])
        skipped_files.extend(file_result["skipped_files"])
    return {
        "retention_days": days,
        "cutoff": cutoff.isoformat(),
        "deleted_images": len(deleted_ids),
        "deleted_image_ids": deleted_ids,
        "deleted_files": deleted_files,
        "missing_files": missing_files,
        "skipped_files": skipped_files,
    }


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
            if result.get("canceled"):
                break
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
    save_enabled = bool(command.settings.get("save_enabled", True))
    filename = f"{captured_at.strftime('%H%M%S')}_{image_id[:8]}.{command.format.lower()}"
    output = (
        settings.image_dir / day_key / filename
        if save_enabled
        else settings.latest_dir / f"latest-unsaved.{command.format.lower()}"
    )
    adapter = get_adapter(cam["adapter"])
    adapter_settings = {**command.settings}
    if cam.get("device_id") and "device_id" not in adapter_settings:
        adapter_settings["device_id"] = cam["device_id"]

    try:
        result, _cancel_result = await capture_with_cancel(
            adapter,
            CaptureRequest(
                output_path=output,
                job_id=job_id,
                exposure_ms=command.exposure_ms,
                gain=command.gain,
                width=command.width,
                height=command.height,
                image_format=command.format,
                mode=command.mode,
                settings=adapter_settings,
            ),
            job_id,
        )
        overlay_result: dict[str, Any] = {"applied": False}
        with session() as conn:
            if overlay_enabled(conn):
                observatory_row = conn.execute("SELECT value FROM system_settings WHERE key='observatory'").fetchone()
                observatory = json_loads(observatory_row["value"], {}) if observatory_row else {}
                overlay_result = apply_overlay(
                    result.file_path,
                    {
                        "observatory_name": observatory.get("name", "Sky Weaver Observatory"),
                        "captured_at": captured_at.isoformat(),
                        "date": captured_at.strftime("%Y-%m-%d"),
                        "time": captured_at.strftime("%H:%M:%S"),
                        "mode": command.mode,
                        "camera_id": cam["id"],
                        "camera_model": cam.get("model") or "",
                        "exposure_ms": result.exposure_ms,
                        "gain": result.gain,
                        "temperature_c": result.temperature_c,
                    },
                    overlay_settings(conn),
                )
        size_bytes = result.file_path.stat().st_size
        metadata = {
            "id": image_id,
            "captured_at": captured_at.isoformat(),
            "camera": {"id": cam["id"], "adapter": cam["adapter"], "model": cam.get("model")},
            "settings": {"exposure_ms": command.exposure_ms, "gain": command.gain, "format": command.format},
            "storage": extract_image_metadata(result.file_path),
            "environment": {"sensor_temperature_c": result.temperature_c, "system_temperature_c": read_pi_temp()},
            "analysis": analyze_image(result.file_path),
            "overlay": overlay_result,
            **result.metadata,
        }
        sidecar = Path(str(result.file_path) + ".json")
        sidecar.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        thumb = make_thumbnail(
            result.file_path,
            settings.thumbnail_dir / day_key / result.file_path.name if save_enabled else settings.latest_dir / f"latest-unsaved-thumbnail.{result.format.lower()}",
        )

        with session() as conn:
            state = conn.execute("SELECT status, updated_at FROM capture_state WHERE id=1").fetchone()
            job = conn.execute("SELECT started_at FROM capture_jobs WHERE id=?", (job_id,)).fetchone()
            stopped_after_start = bool(
                state
                and job
                and state["status"] == "stopped"
                and state["updated_at"]
                and job["started_at"]
                and state["updated_at"] > job["started_at"]
            )
            image_row = {
                "id": image_id,
                "camera_id": cam["id"],
                "captured_at": captured_at.isoformat(),
                "day_key": day_key,
                "mode": command.mode,
                "file_path": str(result.file_path),
                "public_url": f"/api/v1/images/{image_id}/download",
                "thumbnail_path": str(thumb) if thumb else None,
                "format": result.format,
                "width": result.width,
                "height": result.height,
                "size_bytes": size_bytes,
                "exposure_ms": result.exposure_ms,
                "gain": result.gain,
                "temperature_c": result.temperature_c,
                "mean_brightness": metadata["analysis"]["mean_brightness"],
                "star_count": metadata["analysis"]["star_count"],
                "cloud_score": metadata["analysis"]["cloud_score"],
                "bad_image": int(metadata["analysis"]["bad_image"]),
                "overlay_applied": int(bool(overlay_result.get("applied"))),
                "metadata": metadata,
                "created_at": now_iso(),
            }
            publish_payload = publish_latest_image(image_row, metadata, thumb)
            if save_enabled:
                conn.execute(
                    """INSERT INTO images
                       (id, camera_id, captured_at, day_key, mode, file_path, public_url, thumbnail_path, format, width, height,
                        size_bytes, exposure_ms, gain, temperature_c, mean_brightness, star_count, cloud_score, bad_image, overlay_applied, metadata, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        image_row["id"],
                        image_row["camera_id"],
                        image_row["captured_at"],
                        image_row["day_key"],
                        image_row["mode"],
                        image_row["file_path"],
                        image_row["public_url"],
                        image_row["thumbnail_path"],
                        image_row["format"],
                        image_row["width"],
                        image_row["height"],
                        image_row["size_bytes"],
                        image_row["exposure_ms"],
                        image_row["gain"],
                        image_row["temperature_c"],
                        image_row["mean_brightness"],
                        image_row["star_count"],
                        image_row["cloud_score"],
                        image_row["bad_image"],
                        image_row["overlay_applied"],
                        json_dumps(metadata),
                        image_row["created_at"],
                    ),
                )
                conn.execute(
                    "UPDATE capture_state SET last_image_id=?, active_camera_id=?, daemon_last_success_at=?, last_error=NULL, updated_at=? WHERE id=1",
                    (image_id, cam["id"], now_iso(), now_iso()),
                )
                job_result = {"image_id": image_id}
                event_payload = {"image_id": image_id, "path": str(result.file_path), "public_latest": publish_payload}
                event_type = "new_image"
            else:
                conn.execute(
                    "UPDATE capture_state SET active_camera_id=?, daemon_last_success_at=?, last_error=NULL, updated_at=? WHERE id=1",
                    (cam["id"], now_iso(), now_iso()),
                )
                job_result = {"image_id": image_id, "unsaved_latest": True}
                event_payload = {"image_id": image_id, "path": str(result.file_path), "public_latest": publish_payload, "unsaved_latest": True}
                event_type = "latest_image_updated"
            if stopped_after_start:
                job_result.update({"completed_after_stop": True, "stop_mode": "graceful"})
            conn.execute(
                "UPDATE capture_jobs SET status=?, progress=1, result=?, completed_at=? WHERE id=?",
                ("stopped" if stopped_after_start else "completed", json_dumps(job_result), now_iso(), job_id),
            )
            event(conn, event_type, event_payload)

        return {
            "job_id": job_id,
            "image": {
                **metadata,
                "file_path": str(result.file_path),
                "thumbnail_path": str(thumb) if thumb else None,
                "public_latest": publish_payload,
                "unsaved_latest": not save_enabled,
            },
        }
    except CaptureCanceled as exc:
        cancel_result = getattr(exc, "cancel_result", None)
        payload = {
            "stop_mode": "hard_cancel",
            "adapter_cancel_attempted": True,
            "adapter_cancel_result": {
                "supported": bool(cancel_result.supported) if cancel_result else True,
                "canceled": bool(cancel_result.canceled) if cancel_result else True,
                "method": cancel_result.method if cancel_result else None,
                "message": cancel_result.message if cancel_result else str(exc),
            },
        }
        with session() as conn:
            conn.execute("UPDATE capture_state SET status='stopped', last_error=NULL, updated_at=? WHERE id=1", (now_iso(),))
            conn.execute(
                "UPDATE capture_jobs SET status='canceled', progress=1, result=?, error=?, completed_at=? WHERE id=?",
                (json_dumps(payload), "Canceled by operator stop", now_iso(), job_id),
            )
            log(conn, "info", "capture", "Capture canceled by adapter", {"job_id": job_id, **payload})
            event(conn, "capture_canceled", {"job_id": job_id, **payload})
        return {"job_id": job_id, "canceled": True, "result": payload}
    except Exception as exc:
        with session() as conn:
            conn.execute("UPDATE capture_state SET status='error', last_error=?, updated_at=? WHERE id=1", (str(exc), now_iso()))
            conn.execute("UPDATE capture_jobs SET status='failed', error=?, completed_at=? WHERE id=?", (str(exc), now_iso(), job_id))
            log(conn, "error", "capture", "Capture failed", {"error": str(exc), "camera_id": cam["id"]})
            event(conn, "camera_error", {"error": str(exc), "camera_id": cam["id"]})
        raise


def profile_for_mode(conn, camera_id: str, mode: str) -> dict[str, Any] | None:
    profile_mode = CAPTURE_MODE_TO_PROFILE.get(mode, mode)
    row = conn.execute(
        "SELECT * FROM camera_profiles WHERE camera_id=? AND mode=? ORDER BY updated_at DESC LIMIT 1",
        (camera_id, profile_mode),
    ).fetchone()
    return decode_row(row_to_dict(row))


def schedule_command(camera_id: str | None = None, mode: str = "night") -> CaptureCommand:
    with session() as conn:
        camera = get_primary_camera(conn, camera_id)
        profile = profile_for_mode(conn, camera["id"], mode)
    settings = profile["settings"] if profile else {}
    return CaptureCommand(
        camera_id=camera["id"],
        exposure_ms=float(settings.get("manual_exposure_ms", 1000)),
        gain=float(settings.get("gain", 1.0)),
        width=settings.get("width", 1280),
        height=settings.get("height", 960),
        format=settings.get("format", "jpg"),
        mode=mode,
        settings=settings,
    )


def capture_interval_seconds(mode: str | None = None, camera_id: str | None = None) -> int:
    with session() as conn:
        camera = get_primary_camera(conn, camera_id) if mode else None
        profile = profile_for_mode(conn, camera["id"], mode) if camera and mode else None
        row = conn.execute("SELECT interval_seconds FROM capture_schedule LIMIT 1").fetchone()
    fallback = int(row["interval_seconds"]) if row else 30
    settings = profile["settings"] if profile else {}
    return max(1, int(settings.get("interval_seconds") or fallback))


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def latest_completed_scheduled_capture_at(mode: str | None = None) -> datetime | None:
    with session() as conn:
        rows = conn.execute(
            "SELECT request, completed_at FROM capture_jobs WHERE type='scheduled' AND status='completed' AND completed_at IS NOT NULL ORDER BY completed_at DESC LIMIT 200"
        ).fetchall()
    for row in rows:
        decoded = decode_row(row_to_dict(row)) or {}
        request = decoded.get("request") if isinstance(decoded.get("request"), dict) else {}
        if mode is None or request.get("mode") == mode:
            return parse_timestamp(decoded.get("completed_at"))
    return None


def scheduled_capture_timing(mode: str, now: datetime | None = None, camera_id: str | None = None) -> dict[str, Any]:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    interval = capture_interval_seconds(mode, camera_id)
    last_capture_at = latest_completed_scheduled_capture_at(mode)
    due_at = last_capture_at + timedelta(seconds=interval) if last_capture_at else current
    capture_enabled = scheduled_capture_enabled(mode, camera_id)
    command = schedule_command(camera_id, mode)
    save_enabled = bool(command.settings.get("save_enabled", True))
    due = current >= due_at
    return {
        "capture_mode": mode,
        "capture_enabled": capture_enabled,
        "save_enabled": save_enabled,
        "interval_seconds": interval,
        "last_scheduled_capture_at": last_capture_at.isoformat() if last_capture_at else None,
        "next_capture_due_at": due_at.isoformat(),
        "capture_due": due,
        "seconds_until_due": max(0, int((due_at - current).total_seconds())),
    }


def scheduled_capture_due(mode: str, now: datetime | None = None, camera_id: str | None = None) -> bool:
    return bool(scheduled_capture_timing(mode, now, camera_id)["capture_due"])


def current_schedule() -> dict[str, Any]:
    with session() as conn:
        row = conn.execute("SELECT * FROM capture_schedule LIMIT 1").fetchone()
    return decode_row(row_to_dict(row)) or {}


def schedule_allows_capture() -> bool:
    schedule = current_schedule()
    return should_capture_now(schedule)


def scheduled_capture_mode() -> str:
    return "night" if schedule_allows_capture() else "day"


def scheduled_capture_enabled(mode: str, camera_id: str | None = None) -> bool:
    with session() as conn:
        camera = get_primary_camera(conn, camera_id)
        profile = profile_for_mode(conn, camera["id"], mode)
    settings = profile["settings"] if profile else {}
    return bool(settings.get("capture_enabled", False))


def latest_saved_night_day_key() -> str | None:
    with session() as conn:
        row = conn.execute("SELECT day_key FROM images WHERE mode='night' ORDER BY captured_at DESC LIMIT 1").fetchone()
    return row["day_key"] if row else None


def last_scheduled_mode_state() -> str | None:
    with session() as conn:
        row = conn.execute("SELECT value FROM system_settings WHERE key='capture_daemon_last_schedule_mode'").fetchone()
    value = json_loads(row["value"], None) if row else None
    return value if value in {"day", "night"} else None


def set_scheduled_mode_state(mode: str) -> None:
    with session() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('capture_daemon_last_schedule_mode', ?, ?)",
            (json_dumps(mode), now_iso()),
        )


def queue_end_of_night_products(day_key: str, profile_settings: dict[str, Any]) -> list[dict[str, Any]]:
    product_flags = {
        "keogram": "end_of_night_keogram",
        "startrail": "end_of_night_startrail",
        "timelapse": "end_of_night_timelapse",
        "mini_timelapse": "end_of_night_mini_timelapse",
    }
    requested = [job_type for job_type, key in product_flags.items() if bool(profile_settings.get(key))]
    if not requested or not bool(profile_settings.get("save_enabled", True)):
        return []

    queued: list[dict[str, Any]] = []
    with session() as conn:
        marker_key = f"end_of_night_products:{day_key}"
        existing = conn.execute("SELECT value FROM system_settings WHERE key=?", (marker_key,)).fetchone()
        if existing:
            return []
        for job_type in requested:
            job_id = new_id()
            payload = {"day_key": day_key, "source": "end_of_night"}
            conn.execute(
                "INSERT INTO processing_jobs (id, type, status, input, created_at) VALUES (?, ?, 'pending', ?, ?)",
                (job_id, job_type, json_dumps(payload), now_iso()),
            )
            queued.append({"id": job_id, "type": job_type, "status": "pending", "input": payload})
        conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES (?, ?, ?)", (marker_key, json_dumps({"queued": queued}), now_iso()))
        event(conn, "end_of_night_products_queued", {"day_key": day_key, "jobs": queued})
    return queued


def night_profile_settings(camera_id: str | None = None) -> dict[str, Any]:
    with session() as conn:
        camera = get_primary_camera(conn, camera_id)
        profile = profile_for_mode(conn, camera["id"], "night")
    return profile["settings"] if profile else {}


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


def metadata_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, tuple):
        return [metadata_value(item) for item in value]
    if isinstance(value, list):
        return [metadata_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): metadata_value(item) for key, item in value.items()}
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        try:
            return float(value)
        except (TypeError, ZeroDivisionError):
            return str(value)
    return str(value)


def extract_exif_metadata(img: Image.Image) -> dict[str, Any]:
    try:
        exif = img.getexif()
    except Exception:
        return {}
    if not exif:
        return {}
    metadata: dict[str, Any] = {}
    for tag_id, value in exif.items():
        tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
        if tag_name == "MakerNote":
            continue
        if tag_name == "GPSInfo" and isinstance(value, dict):
            metadata[tag_name] = {ExifTags.GPSTAGS.get(key, str(key)): metadata_value(item) for key, item in value.items()}
            continue
        metadata[tag_name] = metadata_value(value)
    return metadata


def extract_image_metadata(path: Path) -> dict[str, Any]:
    stat = path.stat()
    with Image.open(path) as img:
        return {
            "file": {
                "name": path.name,
                "suffix": path.suffix.lower(),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
            },
            "image": {
                "format": img.format,
                "mode": img.mode,
                "width": img.width,
                "height": img.height,
                "has_transparency": img.mode in {"RGBA", "LA"} or "transparency" in img.info,
            },
            "exif": extract_exif_metadata(img),
        }


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
