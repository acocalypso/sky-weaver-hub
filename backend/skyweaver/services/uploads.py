import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..db import event, json_dumps, json_loads, log, new_id, now_iso, row_to_dict, session
from .capture import decode_row

SUPPORTED_TARGET_TYPES = {"filesystem", "rsync_ssh", "scp_ssh"}
SUPPORTED_SOURCE_TYPES = {"image", "product", "latest"}
SAFE_REMOTE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-/")
SAFE_HOST_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")
SAFE_USER_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


def safe_target_config(config: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in config.items():
        lowered = key.lower()
        if lowered == "ssh_key_path":
            safe[key] = value
        elif any(secret in lowered for secret in ("password", "secret", "token", "key")):
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
    if target_type == "rsync":
        target_type = "rsync_ssh"
    if target_type == "scp":
        target_type = "scp_ssh"
    if target_type not in SUPPORTED_TARGET_TYPES:
        raise ValueError("Remote target type is not supported")
    if target_type in {"rsync_ssh", "scp_ssh"}:
        return name, target_type, validate_ssh_config(config, target_type), bool(payload.get("enabled", False))
    destination = str(config.get("destination_path") or config.get("path") or "").strip()
    if not destination:
        raise ValueError("Filesystem remote targets require config.destination_path")
    normalized_config = {"destination_path": destination}
    return name, target_type, normalized_config, bool(payload.get("enabled", False))


def validate_rsync_ssh_config(config: dict[str, Any]) -> dict[str, Any]:
    return validate_ssh_config(config, "rsync_ssh")


def validate_ssh_config(config: dict[str, Any], target_type: str) -> dict[str, Any]:
    host = str(config.get("host") or "").strip()
    username = str(config.get("username") or config.get("user") or "").strip()
    remote_path = str(config.get("remote_path") or config.get("path") or "").strip().rstrip("/")
    ssh_key_path = str(config.get("ssh_key_path") or "").strip()
    try:
        port = int(config.get("port") or 22)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{target_type} target requires a numeric port") from exc
    if not host or not username or not remote_path:
        raise ValueError(f"{target_type} targets require config.host, config.username, and config.remote_path")
    if port < 1 or port > 65535:
        raise ValueError(f"{target_type} port must be between 1 and 65535")
    if not set(host) <= SAFE_HOST_CHARS or host.startswith("-"):
        raise ValueError(f"{target_type} host contains unsupported characters")
    if not set(username) <= SAFE_USER_CHARS or username.startswith("-"):
        raise ValueError(f"{target_type} username contains unsupported characters")
    if not set(remote_path) <= SAFE_REMOTE_CHARS or remote_path.startswith("-"):
        raise ValueError(f"{target_type} remote_path contains unsupported characters")
    normalized: dict[str, Any] = {"host": host, "username": username, "remote_path": remote_path, "port": port}
    if ssh_key_path:
        if not set(ssh_key_path) <= SAFE_REMOTE_CHARS or ssh_key_path.startswith("-"):
            raise ValueError(f"{target_type} ssh_key_path contains unsupported characters")
        normalized["ssh_key_path"] = ssh_key_path
    return normalized


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
        destination = copy_to_target(upload, target)
        with session() as conn:
            conn.execute("UPDATE upload_jobs SET status='completed', destination_path=?, completed_at=? WHERE id=?", (destination, now_iso(), upload_id))
            event(conn, "upload_completed", {"upload_job_id": upload_id, "target_id": target["id"], "destination_path": destination})
        return {"upload_job_id": upload_id, "destination_path": destination}
    except Exception as exc:
        with session() as conn:
            conn.execute("UPDATE upload_jobs SET status='failed', last_error=?, completed_at=? WHERE id=?", (str(exc), now_iso(), upload_id))
            event(conn, "upload_failed", {"upload_job_id": upload_id, "target_id": upload["target_id"], "error": str(exc)})
        raise


def copy_to_target(upload: dict[str, Any], target: dict[str, Any]) -> str:
    if target.get("type") == "filesystem":
        return str(copy_to_filesystem_target(upload, target))
    if target.get("type") == "rsync_ssh":
        return copy_to_rsync_ssh_target(upload, target)
    if target.get("type") == "scp_ssh":
        return copy_to_scp_ssh_target(upload, target)
    raise ValueError("Remote target type is not supported")


def target_config(target: dict[str, Any]) -> dict[str, Any]:
    config = target.get("config_encrypted")
    if isinstance(config, str):
        config = json_loads(config, {})
    if not isinstance(config, dict):
        config = {}
    return config


def copy_to_filesystem_target(upload: dict[str, Any], target: dict[str, Any]) -> Path:
    config = target_config(target)
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


def copy_to_rsync_ssh_target(upload: dict[str, Any], target: dict[str, Any]) -> str:
    config = validate_rsync_ssh_config(target_config(target))
    source = Path(upload["source_path"])
    if not source.exists():
        raise FileNotFoundError(source)
    if shutil.which("rsync") is None:
        raise RuntimeError("rsync is not installed")
    if shutil.which("ssh") is None:
        raise RuntimeError("ssh is not installed")
    destination_dir = f"{config['remote_path']}/{upload['source_type']}/{upload['source_id']}"
    remote = f"{config['username']}@{config['host']}:{destination_dir}/{source.name}"
    ssh_parts = ["ssh", "-p", str(config["port"]), "-o", "BatchMode=yes"]
    if config.get("ssh_key_path"):
        ssh_parts.extend(["-i", str(config["ssh_key_path"])])
    command = ["rsync", "-az", "--mkpath", "-e", " ".join(ssh_parts), str(source), remote]
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"rsync upload failed with exit code {result.returncode}: {stderr}")
    return f"rsync://{config['username']}@{config['host']}:{destination_dir}/{source.name}"


def copy_to_scp_ssh_target(upload: dict[str, Any], target: dict[str, Any]) -> str:
    config = validate_ssh_config(target_config(target), "scp_ssh")
    source = Path(upload["source_path"])
    if not source.exists():
        raise FileNotFoundError(source)
    if shutil.which("ssh") is None:
        raise RuntimeError("ssh is not installed")
    if shutil.which("scp") is None:
        raise RuntimeError("scp is not installed")
    destination_dir = f"{config['remote_path']}/{upload['source_type']}/{upload['source_id']}"
    remote = f"{config['username']}@{config['host']}:{destination_dir}/{source.name}"
    ssh_base = ["-P", str(config["port"]), "-o", "BatchMode=yes"]
    ssh_command = ["ssh", "-p", str(config["port"]), "-o", "BatchMode=yes"]
    if config.get("ssh_key_path"):
        ssh_base.extend(["-i", str(config["ssh_key_path"])])
        ssh_command.extend(["-i", str(config["ssh_key_path"])])
    mkdir_result = subprocess.run(
        [*ssh_command, f"{config['username']}@{config['host']}", "mkdir", "-p", destination_dir],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if mkdir_result.returncode != 0:
        stderr = (mkdir_result.stderr or mkdir_result.stdout or "").strip()
        raise RuntimeError(f"scp target directory creation failed with exit code {mkdir_result.returncode}: {stderr}")
    result = subprocess.run(["scp", *ssh_base, str(source), remote], capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"scp upload failed with exit code {result.returncode}: {stderr}")
    return f"scp://{config['username']}@{config['host']}:{destination_dir}/{source.name}"


def test_target(target: dict[str, Any]) -> dict[str, Any]:
    if target.get("type") == "filesystem":
        config = target_config(target)
        destination = Path(str(config.get("destination_path", ""))).expanduser()
        try:
            destination.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ValueError(f"Target path is not writable: {exc}") from exc
        return {"id": target["id"], "status": "ready", "type": target["type"], "destination_path": str(destination)}
    if target.get("type") in {"rsync_ssh", "scp_ssh"}:
        config = validate_ssh_config(target_config(target), str(target.get("type")))
        binaries = ("rsync", "ssh") if target.get("type") == "rsync_ssh" else ("scp", "ssh")
        missing = [binary for binary in binaries if shutil.which(binary) is None]
        if missing:
            raise ValueError(f"Missing required command(s): {', '.join(missing)}")
        return {
            "id": target["id"],
            "status": "configured",
            "type": target["type"],
            "destination_path": f"{'rsync' if target.get('type') == 'rsync_ssh' else 'scp'}://{config['username']}@{config['host']}:{config['remote_path']}",
        }
    raise ValueError("Remote target type is not supported")


def update_parent_progress(job_id: str, progress: float) -> None:
    with session() as conn:
        conn.execute("UPDATE processing_jobs SET progress=? WHERE id=?", (max(0, min(1, progress)), job_id))
