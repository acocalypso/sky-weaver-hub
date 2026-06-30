import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from ..config import get_settings
from ..db import event, json_dumps, json_loads, new_id, now_iso, row_to_dict, session
from .capture import analyze_image, decode_row, delete_image_files, delete_storage_paths, extract_image_metadata, make_thumbnail

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
VIDEO_SUFFIXES = {".mp4", ".webm"}
DATE_PATTERNS = (
    re.compile(r"(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)"),
    re.compile(r"([01]\d)[-_]?([0-3]\d)[-_]?(20\d{2})"),
)
CONFIG_NAMES = {"config.sh", "settings.json", "options.json", "camera_settings.json", "ftp-settings.sh", "ftp-settings.json", "variables.sh"}
TRANSLATABLE_KEYS = {
    "latitude",
    "lat",
    "longitude",
    "lon",
    "lng",
    "angle",
    "sunangle",
    "timezone",
    "timezone",
    "tz",
    "location",
    "sitename",
    "title",
    "hostname",
    "camera",
    "cameratype",
    "cameratype",
    "cameramodel",
    "cameramodel",
    "publicpage",
    "publicpage",
    "website",
    "usewebsite",
}


def preview_allsky_root(root: Path) -> dict[str, Any]:
    files = scan_allsky_files(root)
    settings_preview = preview_settings(root)
    return {
        "path": str(root),
        "exists": root.exists(),
        "counts": {
            "images": len(files["images"]),
            "timelapses": len(files["timelapses"]),
            "keograms": len(files["keograms"]),
            "startrails": len(files["startrails"]),
        },
        "unsupported_settings": settings_preview["unsupported_settings"],
        "settings": settings_preview["settings"],
        "will_delete_original": False,
        "import_plan": {
            "copy_files": True,
            "preserve_originals": True,
            "rollback_supported": True,
        },
    }


def scan_allsky_files(root: Path) -> dict[str, list[Path]]:
    buckets: dict[str, list[Path]] = {"images": [], "timelapses": [], "keograms": [], "startrails": []}
    if not root.exists() or not root.is_dir():
        return buckets
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        name = path.name.lower()
        suffix = path.suffix.lower()
        if suffix in VIDEO_SUFFIXES:
            buckets["timelapses"].append(path)
        elif suffix in IMAGE_SUFFIXES and "keogram" in name:
            buckets["keograms"].append(path)
        elif suffix in IMAGE_SUFFIXES and "startrail" in name:
            buckets["startrails"].append(path)
        elif suffix in IMAGE_SUFFIXES:
            buckets["images"].append(path)
    return buckets


def unsupported_settings(root: Path) -> list[dict[str, str]]:
    if not root.exists() or not root.is_dir():
        return []
    findings: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name.lower() in CONFIG_NAMES:
            findings.append({
                "path": str(path),
                "reason": "partially_supported_config_file",
            })
    return findings


def preview_settings(root: Path) -> dict[str, Any]:
    parsed = read_allsky_settings(root)
    mapped = map_allsky_settings(parsed)
    unsupported = []
    for item in unsupported_settings(root):
        unsupported.append(item)
    for key, value in parsed.items():
        if normalize_key(key) not in TRANSLATABLE_KEYS:
            unsupported.append({"path": value["path"], "key": key, "reason": "setting_not_mapped"})
    return {"settings": mapped, "unsupported_settings": unsupported}


def execute_allsky_import(job: dict[str, Any]) -> dict[str, Any]:
    root = Path(str(job.get("input", {}).get("path", ""))).expanduser()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(root)
    files = scan_allsky_files(root)
    imported_images = [import_image(path, job["id"]) for path in files["images"]]
    imported_products = [
        *(import_product(path, job["id"], "keogram") for path in files["keograms"]),
        *(import_product(path, job["id"], "startrail") for path in files["startrails"]),
        *(import_product(path, job["id"], "timelapse") for path in files["timelapses"]),
    ]
    settings_result = apply_allsky_settings(root, job["id"])
    with session() as conn:
        event(conn, "allsky_import_completed", {"job_id": job["id"], "images": len(imported_images), "products": len(imported_products)})
    return {
        "migration_job_id": job["id"],
        "imported_images": len(imported_images),
        "imported_products": len(imported_products),
        "image_ids": imported_images,
        "product_ids": imported_products,
        "settings": settings_result,
        "unsupported_settings": preview_settings(root)["unsupported_settings"],
        "will_delete_original": False,
    }


def import_image(source: Path, job_id: str) -> str:
    settings = get_settings()
    captured_at = datetime.fromtimestamp(source.stat().st_mtime, UTC)
    day_key = infer_day_key(source, captured_at)
    image_id = new_id()
    suffix = normalized_image_suffix(source)
    target = settings.image_dir / day_key / f"allsky_{captured_at.strftime('%H%M%S')}_{image_id[:8]}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    thumbnail = make_thumbnail(target, settings.thumbnail_dir / day_key / target.name)
    sidecar = Path(str(target) + ".json")
    width = height = None
    image_format = suffix.lstrip(".")
    try:
        with Image.open(target) as img:
            width, height = img.width, img.height
            image_format = (img.format or image_format).lower()
    except Exception:
        pass
    analysis = analyze_image(target)
    metadata = {
        "id": image_id,
        "captured_at": captured_at.isoformat(),
        "storage": extract_image_metadata(target),
        "analysis": analysis,
        "migration": {"source": "allsky", "job_id": job_id, "original_path": str(source)},
    }
    sidecar.write_text(json_dumps(metadata), encoding="utf-8")
    with session() as conn:
        conn.execute(
            """INSERT INTO images
               (id, camera_id, captured_at, day_key, mode, file_path, public_url, thumbnail_path, format, width, height,
                size_bytes, exposure_ms, gain, temperature_c, mean_brightness, star_count, cloud_score, bad_image, overlay_applied, metadata, created_at)
               VALUES (?, NULL, ?, ?, 'imported', ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, ?, ?, 0, ?, ?)""",
            (
                image_id,
                captured_at.isoformat(),
                day_key,
                str(target),
                f"/api/v1/images/{image_id}/download",
                str(thumbnail) if thumbnail else None,
                image_format,
                width,
                height,
                target.stat().st_size,
                analysis["mean_brightness"],
                analysis["star_count"],
                analysis["cloud_score"],
                int(analysis["bad_image"]),
                json_dumps(metadata),
                now_iso(),
            ),
        )
        event(conn, "allsky_image_imported", {"job_id": job_id, "image_id": image_id, "original_path": str(source)})
    return image_id


def import_product(source: Path, job_id: str, product_type: str) -> str:
    settings = get_settings()
    created_at = datetime.fromtimestamp(source.stat().st_mtime, UTC)
    day_key = infer_day_key(source, created_at)
    product_id = new_id()
    target = settings.product_dir / day_key / f"allsky_{product_type}_{product_id[:8]}{source.suffix.lower()}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    thumbnail = make_thumbnail(target, settings.thumbnail_dir / day_key / f"{target.stem}.jpg") if source.suffix.lower() in IMAGE_SUFFIXES else None
    metadata = {
        "day_key": day_key,
        "migration": {"source": "allsky", "job_id": job_id, "original_path": str(source)},
    }
    with session() as conn:
        conn.execute(
            "INSERT INTO night_products (id, type, day_key, file_path, thumbnail_path, status, metadata, created_at) VALUES (?, ?, ?, ?, ?, 'completed', ?, ?)",
            (product_id, product_type, day_key, str(target), str(thumbnail) if thumbnail else None, json_dumps(metadata), created_at.isoformat()),
        )
        event(conn, "allsky_product_imported", {"job_id": job_id, "product_id": product_id, "type": product_type, "original_path": str(source)})
    return product_id


def rollback_allsky_import(job_id: str) -> dict[str, Any]:
    with session() as conn:
        job = decode_row(row_to_dict(conn.execute("SELECT output FROM processing_jobs WHERE id=?", (job_id,)).fetchone()))
        settings_restore = restore_settings_from_job_output(conn, job)
        images = [
            decode_row(row_to_dict(row))
            for row in conn.execute("SELECT * FROM images ORDER BY created_at DESC").fetchall()
        ]
        products = [
            decode_row(row_to_dict(row))
            for row in conn.execute("SELECT * FROM night_products ORDER BY created_at DESC").fetchall()
        ]
        images = [image for image in images if migration_job_id(image) == job_id]
        products = [product for product in products if migration_job_id(product) == job_id]
        deleted_files: list[str] = []
        missing_files: list[str] = []
        skipped_files: list[dict[str, Any]] = []
        image_ids: list[str] = []
        product_ids: list[str] = []
        for image in images:
            result = delete_image_files(image)
            conn.execute("DELETE FROM images WHERE id=?", (image["id"],))
            image_ids.append(image["id"])
            deleted_files.extend(result["deleted_files"])
            missing_files.extend(result["missing_files"])
            skipped_files.extend(result["skipped_files"])
        for product in products:
            result = delete_storage_paths(product_storage_artifacts(product))
            conn.execute("DELETE FROM night_products WHERE id=?", (product["id"],))
            product_ids.append(product["id"])
            deleted_files.extend(result["deleted_files"])
            missing_files.extend(result["missing_files"])
            skipped_files.extend(result["skipped_files"])
        event(conn, "allsky_import_rolled_back", {"job_id": job_id, "images": len(image_ids), "products": len(product_ids)})
    return {
        "migration_job_id": job_id,
        "deleted_images": len(image_ids),
        "deleted_products": len(product_ids),
        "deleted_image_ids": image_ids,
        "deleted_product_ids": product_ids,
        "deleted_files": deleted_files,
        "missing_files": missing_files,
        "skipped_files": skipped_files,
        "settings_restored": settings_restore,
    }


def read_allsky_settings(root: Path) -> dict[str, dict[str, Any]]:
    settings: dict[str, dict[str, Any]] = {}
    if not root.exists() or not root.is_dir():
        return settings
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.lower() not in CONFIG_NAMES:
            continue
        if path.suffix.lower() == ".json":
            values = read_json_settings(path)
        else:
            values = read_shell_settings(path)
        for key, value in values.items():
            settings[key] = {"value": value, "path": str(path)}
    return settings


def read_json_settings(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    flattened: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                flattened[f"{key}.{child_key}"] = child_value
        else:
            flattened[str(key)] = value
    return flattened


def read_shell_settings(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return values
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        if text.startswith("export "):
            text = text[len("export "):].strip()
        key, value = text.split("=", 1)
        key = key.strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            continue
        values[key] = value.strip().strip("\"'")
    return values


def map_allsky_settings(parsed: dict[str, dict[str, Any]]) -> dict[str, Any]:
    lookup = {normalize_key(key): item["value"] for key, item in parsed.items()}
    mapped: dict[str, Any] = {}
    latitude = first_float(lookup, ("latitude", "lat"))
    longitude = first_float(lookup, ("longitude", "lon", "lng"))
    timezone = first_text(lookup, ("timezone", "time_zone", "tz"))
    name = first_text(lookup, ("location", "sitename", "title", "hostname"))
    angle = first_float(lookup, ("angle", "sunangle"))
    public_enabled = first_bool(lookup, ("publicpage", "public_page", "website", "usewebsite"))
    camera_hint = first_text(lookup, ("camera", "cameratype", "camera_type", "cameramodel", "camera_model"))
    observatory: dict[str, Any] = {}
    if latitude is not None and -90 <= latitude <= 90:
        observatory["latitude"] = latitude
    if longitude is not None and -180 <= longitude <= 180:
        observatory["longitude"] = longitude
    if timezone:
        observatory["timezone"] = timezone
    if name:
        observatory["name"] = name
    if observatory:
        mapped["observatory"] = observatory
    if angle is not None and -30 <= angle <= 30:
        mapped["schedule"] = {"sun_angle": angle, "start_sun_angle": angle, "end_sun_angle": angle}
    if public_enabled is not None:
        mapped["public_page"] = {"enabled": public_enabled}
    if camera_hint:
        mapped["camera_hints"] = {"source": "allsky", "hint": camera_hint}
    return mapped


def apply_allsky_settings(root: Path, job_id: str) -> dict[str, Any]:
    mapped = map_allsky_settings(read_allsky_settings(root))
    backup: dict[str, Any] = {}
    with session() as conn:
        for key in ("observatory", "public_page", "allsky_camera_hints"):
            row = conn.execute("SELECT value FROM system_settings WHERE key=?", (key,)).fetchone()
            backup[key] = json_loads(row["value"], None) if row else None
        schedule_row = row_to_dict(conn.execute("SELECT * FROM capture_schedule LIMIT 1").fetchone())
        backup["capture_schedule"] = schedule_row

        if "observatory" in mapped:
            current = backup.get("observatory") if isinstance(backup.get("observatory"), dict) else {}
            value = {**current, **mapped["observatory"]}
            conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('observatory', ?, ?)", (json_dumps(value), now_iso()))
        if "public_page" in mapped:
            current = backup.get("public_page") if isinstance(backup.get("public_page"), dict) else {}
            value = {**current, **mapped["public_page"]}
            conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('public_page', ?, ?)", (json_dumps(value), now_iso()))
        if "camera_hints" in mapped:
            value = {**mapped["camera_hints"], "job_id": job_id}
            conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('allsky_camera_hints', ?, ?)", (json_dumps(value), now_iso()))
        if "schedule" in mapped:
            if schedule_row:
                patch = mapped["schedule"]
                conn.execute(
                    "UPDATE capture_schedule SET sun_angle=?, start_sun_angle=?, end_sun_angle=?, updated_at=? WHERE id=?",
                    (patch["sun_angle"], patch["start_sun_angle"], patch["end_sun_angle"], now_iso(), schedule_row["id"]),
                )
        if mapped:
            event(conn, "allsky_settings_imported", {"job_id": job_id, "settings_keys": sorted(mapped.keys())})
    return {"applied": mapped, "backup": backup}


def restore_settings_from_job_output(conn, job: dict[str, Any] | None) -> dict[str, Any]:
    output = job.get("output") if job else None
    if not isinstance(output, dict):
        return {"restored": False, "reason": "missing_job_output"}
    settings_result = output.get("settings")
    if not isinstance(settings_result, dict):
        return {"restored": False, "reason": "missing_settings_backup"}
    backup = settings_result.get("backup")
    if not isinstance(backup, dict):
        return {"restored": False, "reason": "missing_settings_backup"}
    restored: list[str] = []
    for key in ("observatory", "public_page", "allsky_camera_hints"):
        value = backup.get(key)
        if value is None:
            conn.execute("DELETE FROM system_settings WHERE key=?", (key,))
        else:
            conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES (?, ?, ?)", (key, json_dumps(value), now_iso()))
        restored.append(key)
    schedule = backup.get("capture_schedule")
    if isinstance(schedule, dict) and schedule.get("id"):
        conn.execute(
            """UPDATE capture_schedule SET enabled=?, start_mode=?, end_mode=?, sun_angle=?, start_sun_angle=?, end_sun_angle=?,
               fixed_start_time=?, fixed_end_time=?, timezone=?, latitude=?, longitude=?, interval_seconds=?, exposure_ramping_enabled=?, updated_at=? WHERE id=?""",
            (
                schedule["enabled"], schedule["start_mode"], schedule["end_mode"], schedule["sun_angle"], schedule.get("start_sun_angle"), schedule.get("end_sun_angle"),
                schedule.get("fixed_start_time"), schedule.get("fixed_end_time"), schedule["timezone"], schedule["latitude"], schedule["longitude"],
                schedule["interval_seconds"], schedule["exposure_ramping_enabled"], now_iso(), schedule["id"],
            ),
        )
        restored.append("capture_schedule")
    return {"restored": True, "settings_keys": restored}


def migration_job_id(row: dict[str, Any]) -> str | None:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    migration = metadata.get("migration") if isinstance(metadata.get("migration"), dict) else {}
    return migration.get("job_id")


def product_storage_artifacts(product: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for key in ("file_path", "thumbnail_path"):
        value = product.get(key)
        if value:
            paths.append(Path(str(value)))
    return paths


def infer_day_key(path: Path, fallback: datetime) -> str:
    candidate = " ".join(str(part) for part in (*path.parts[-4:], path.stem))
    for pattern in DATE_PATTERNS:
        match = pattern.search(candidate)
        if not match:
            continue
        groups = match.groups()
        if groups[0].startswith("20"):
            year, month, day = groups
        else:
            month, day, year = groups
        try:
            datetime(int(year), int(month), int(day))
        except ValueError:
            continue
        return f"{year}{month}{day}"
    return fallback.strftime("%Y%m%d")


def normalized_image_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    return ".jpg" if suffix == ".jpeg" else suffix


def normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


def first_text(values: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = values.get(normalize_key(key))
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def first_float(values: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    text = first_text(values, keys)
    if not text:
        return None
    cleaned = text.strip().upper()
    multiplier = -1 if cleaned.endswith(("S", "W")) else 1
    cleaned = cleaned.rstrip("NSEW").strip()
    try:
        return float(cleaned) * multiplier
    except ValueError:
        return None


def first_bool(values: dict[str, Any], keys: tuple[str, ...]) -> bool | None:
    text = first_text(values, keys)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in {"1", "true", "yes", "y", "on", "enabled", "enable"}:
        return True
    if lowered in {"0", "false", "no", "n", "off", "disabled", "disable"}:
        return False
    return None
