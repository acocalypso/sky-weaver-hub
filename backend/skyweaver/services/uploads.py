import shutil
from pathlib import Path
from typing import Any

from ..db import event, json_dumps, json_loads, log, new_id, now_iso, row_to_dict, session
from .capture import decode_row

SUPPORTED_TARGET_TYPES = {"filesystem"}
SUPPORTED_SOURCE_TYPES = {"image", "product", "latest"}


def safe_target_config(config: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in config.items():
        lowered = key.lower()
        if any(secret in lowered for secret in ("password", "secret", "token", "key")):
            safe[key] = "***"
        else:
            safe[key] = value
    return safe


def remote_target_payload(row: dict[str, Any]) -> dict[str, Any]:
    config = row.get("config_encrypted")
    if isinstance(config, str):
        config = json_loads(config, {})
    if not isinstance(config, dict):
        config = {}
    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "enabled": bool(row["enabled"]),
        "config": safe_target_config(config),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def validate_target_payload(payload: dict[str, Any]) -> tuple[str, str, dict[str, Any], bool]:
    name = str(payload.get("name") or "").strip()
    target_type = str(payload.get("type") or "").strip().lower()
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    if not name:
        raise ValueError("Remote target name is required")
    if target_type not in SUPPORTED_TARGET_TYPES:
        raise ValueError("Only filesystem remote targets are implemented")
    destination = str(config.get("destination_path") or config.get("path") or "").strip()
    if not destination:
        raise ValueError("Filesystem remote targets require config.destination_path")
    normalized_config = {"destination_path": destination}
    return name, target_type, normalized_config, bool(payload.get("enabled", False))


def resolve_source(conn, source_type: str, source_id: str | None = None) -> dict[str, Any]:
    source_type = source_type.replace("-", "_")
    if source_type not in SUPPORTED_SOURCE_TYPES:
        raise ValueError("Unsupported upload source type")
    if source_type == "latest":
        row = conn.execute("SELECT * FROM images ORDER BY captured_at DESC LIMIT 1").fetchone()
        source_type = "image"
    elif source_type == "image":
        if not source_id:
            raise ValueError("image upload requires source_id")
        row = conn.execute("SELECT * FROM images WHERE id=?", (source_id,)).fetchone()
    else:
        if not source_id:
            raise ValueError("product upload requires source_id")
        row = conn.execute("SELECT * FROM night_products WHERE id=?", (source_id,)).fetchone()
    source = decode_row(row_to_dict(row))
    if not source:
        raise LookupError("Upload source not found")
    source_path = Path(source["file_path"])
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    return {"source_type": source_type, "source_id": source["id"], "source_path": str(source_path), "day_key": source.get("day_key")}


def queue_upload(source_type: str = "latest", source_id: str | None = None, target_id: str | None = None) -> dict[str, Any]:
    with session() as conn:
        source = resolve_source(conn, source_type, source_id)
        target_params: tuple[Any, ...] = (target_id,) if target_id else ()
        target_where = "WHERE id=? AND enabled=1" if target_id else "WHERE enabled=1"
        targets = [decode_row(row_to_dict(row)) for row in conn.execute(f"SELECT * FROM remote_targets {target_where} ORDER BY created_at", target_params).fetchall()]
        targets = [target for target in targets if target and target.get("type") in SUPPORTED_TARGET_TYPES]
        if not targets:
            raise LookupError("No enabled upload targets found")
        upload_ids: list[str] = []
        for target in targets:
            upload_id = new_id()
            conn.execute(
                "INSERT INTO upload_jobs (id, target_id, source_type, source_id, source_path, status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                (upload_id, target["id"], source["source_type"], source["source_id"], source["source_path"], now_iso()),
            )
            upload_ids.append(upload_id)
        processing_id = new_id()
        conn.execute(
            "INSERT INTO processing_jobs (id, type, status, input, created_at) VALUES (?, 'upload', 'pending', ?, ?)",
            (processing_id, json_dumps({"upload_job_ids": upload_ids}), now_iso()),
        )
        conn.execute(
            f"UPDATE upload_jobs SET processing_job_id=? WHERE id IN ({','.join('?' for _ in upload_ids)})",
            (processing_id, *upload_ids),
        )
        event(conn, "uploads_queued", {"processing_job_id": processing_id, "upload_job_ids": upload_ids, "source_type": source["source_type"], "source_id": source["source_id"]})
    return {"id": processing_id, "status": "pending", "upload_job_ids": upload_ids}


def retry_failed_uploads() -> dict[str, Any]:
    with session() as conn:
        rows = [row["id"] for row in conn.execute("SELECT id FROM upload_jobs WHERE status='failed' ORDER BY created_at").fetchall()]
        if not rows:
            return {"status": "idle", "upload_job_ids": [], "processing_job_id": None}
        processing_id = new_id()
        conn.execute(
            "INSERT INTO processing_jobs (id, type, status, input, created_at) VALUES (?, 'upload', 'pending', ?, ?)",
            (processing_id, json_dumps({"upload_job_ids": rows}), now_iso()),
        )
        conn.execute(
            f"UPDATE upload_jobs SET status='pending', last_error=NULL, processing_job_id=? WHERE id IN ({','.join('?' for _ in rows)})",
            (processing_id, *rows),
        )
        event(conn, "uploads_retry_queued", {"processing_job_id": processing_id, "upload_job_ids": rows})
    return {"status": "pending", "processing_job_id": processing_id, "upload_job_ids": rows}


def execute_upload_processing_job(job: dict[str, Any]) -> dict[str, Any]:
    upload_ids = job.get("input", {}).get("upload_job_ids")
    if not isinstance(upload_ids, list) or not upload_ids:
        raise ValueError("upload job requires upload_job_ids")
    completed: list[str] = []
    failed: list[str] = []
    for index, upload_id in enumerate(upload_ids):
        try:
            execute_upload_job(str(upload_id))
            completed.append(str(upload_id))
        except Exception as exc:
            failed.append(str(upload_id))
            with session() as conn:
                log(conn, "error", "upload", "Upload job failed", {"upload_job_id": upload_id, "error": str(exc)})
        update_parent_progress(job["id"], 0.05 + ((index + 1) / len(upload_ids)) * 0.9)
    if failed:
        raise RuntimeError(f"{len(failed)} upload job(s) failed")
    return {"completed_uploads": completed, "failed_uploads": failed}


def execute_upload_job(upload_id: str) -> dict[str, Any]:
    with session() as conn:
        upload = decode_row(row_to_dict(conn.execute("SELECT * FROM upload_jobs WHERE id=?", (upload_id,)).fetchone()))
        if not upload:
            raise LookupError("Upload job not found")
        target = decode_row(row_to_dict(conn.execute("SELECT * FROM remote_targets WHERE id=?", (upload["target_id"],)).fetchone()))
        if not target or not target.get("enabled"):
            raise LookupError("Upload target is disabled or missing")
        conn.execute("UPDATE upload_jobs SET status='running', attempts=attempts+1, started_at=?, last_error=NULL WHERE id=?", (now_iso(), upload_id))
    try:
        destination = copy_to_filesystem_target(upload, target)
        with session() as conn:
            conn.execute("UPDATE upload_jobs SET status='completed', destination_path=?, completed_at=? WHERE id=?", (str(destination), now_iso(), upload_id))
            event(conn, "upload_completed", {"upload_job_id": upload_id, "target_id": target["id"], "destination_path": str(destination)})
        return {"upload_job_id": upload_id, "destination_path": str(destination)}
    except Exception as exc:
        with session() as conn:
            conn.execute("UPDATE upload_jobs SET status='failed', last_error=?, completed_at=? WHERE id=?", (str(exc), now_iso(), upload_id))
            event(conn, "upload_failed", {"upload_job_id": upload_id, "target_id": upload["target_id"], "error": str(exc)})
        raise


def copy_to_filesystem_target(upload: dict[str, Any], target: dict[str, Any]) -> Path:
    config = target.get("config_encrypted")
    if isinstance(config, str):
        config = json_loads(config, {})
    if not isinstance(config, dict):
        config = {}
    destination_root = Path(str(config.get("destination_path") or "")).expanduser()
    if not destination_root:
        raise ValueError("Target destination_path is missing")
    source = Path(upload["source_path"])
    if not source.exists():
        raise FileNotFoundError(source)
    destination = destination_root / upload["source_type"] / upload["source_id"] / source.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def update_parent_progress(job_id: str, progress: float) -> None:
    with session() as conn:
        conn.execute("UPDATE processing_jobs SET progress=? WHERE id=?", (max(0, min(1, progress)), job_id))
