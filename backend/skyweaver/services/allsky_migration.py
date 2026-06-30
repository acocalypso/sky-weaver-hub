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
from .overlay import OVERLAY_MODULE_ID, merge_overlay_settings

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
VIDEO_SUFFIXES = {".mp4", ".webm"}
CAPTURE_DIR_PARTS = {"images", "image", "captures", "photos"}
PRODUCT_DIR_PARTS = {"videos", "video", "timelapse", "timelapses", "keogram", "keograms", "startrail", "startrails"}
EXCLUDED_IMPORT_PARTS = {
    "assets",
    "bower_components",
    "config",
    "config_repo",
    "documentation",
    "html",
    "imagethumbnails",
    "node_modules",
    "overlay",
    "www",
}
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
    "overlay",
    "overlayenabled",
    "showoverlay",
    "showtext",
    "imagetext",
    "imagetextenabled",
    "textline1",
    "textline2",
    "textline3",
    "textline4",
    "overlayline1",
    "overlayline2",
    "overlayline3",
    "overlayline4",
    "fontcolor",
    "textcolor",
    "backgroundcolor",
    "fontsize",
    "font",
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
            "dark_frames": len(files["dark_frames"]),
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
    buckets: dict[str, list[Path]] = {"images": [], "timelapses": [], "keograms": [], "startrails": [], "dark_frames": []}
    if not root.exists() or not root.is_dir():
        return buckets
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        name = path.name.lower()
        suffix = path.suffix.lower()
        if is_excluded_import_path(root, path):
            continue
        if suffix in VIDEO_SUFFIXES and is_allsky_product_path(path, "timelapse"):
            buckets["timelapses"].append(path)
        elif suffix in IMAGE_SUFFIXES and is_dark_frame_path(path):
            buckets["dark_frames"].append(path)
        elif suffix in IMAGE_SUFFIXES and "keogram" in name and is_allsky_product_path(path, "keogram"):
            buckets["keograms"].append(path)
        elif suffix in IMAGE_SUFFIXES and "startrail" in name and is_allsky_product_path(path, "startrail"):
            buckets["startrails"].append(path)
        elif suffix in IMAGE_SUFFIXES and is_allsky_capture_path(path):
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
    unsupported: list[dict[str, Any]] = []
    for item in unsupported_settings(root):
        unsupported.append(item)
    unmapped_by_path: dict[str, list[str]] = {}
    for key, value in parsed.items():
        if normalize_key(key) not in TRANSLATABLE_KEYS:
            unmapped_by_path.setdefault(value["path"], []).append(key)
    for path, keys in sorted(unmapped_by_path.items()):
        unsupported.append({"path": path, "reason": "settings_not_mapped", "keys": sorted(keys), "count": len(keys)})
    return {"settings": mapped, "unsupported_settings": unsupported}


def execute_allsky_import(job: dict[str, Any]) -> dict[str, Any]:
    root = Path(str(job.get("input", {}).get("path", ""))).expanduser()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(root)
    files = scan_allsky_files(root)
    total_steps = max(1, len(files["images"]) + len(files["dark_frames"]) + len(files["keograms"]) + len(files["startrails"]) + len(files["timelapses"]) + 1)
    completed_steps = 0
    import_log: list[dict[str, Any]] = []
    imported_images: list[str] = []
    imported_dark_frames: list[str] = []
    imported_products: list[str] = []

    for path in files["images"]:
        image_id = import_image(path, job["id"])
        imported_images.append(image_id)
        import_log.append({"kind": "image", "id": image_id, "original_path": str(path)})
        completed_steps += 1
        update_allsky_import_progress(job["id"], completed_steps, total_steps)
    for path in files["dark_frames"]:
        frame_id = import_dark_frame(path, job["id"])
        imported_dark_frames.append(frame_id)
        import_log.append({"kind": "dark_frame", "id": frame_id, "original_path": str(path)})
        completed_steps += 1
        update_allsky_import_progress(job["id"], completed_steps, total_steps)
    for product_type, paths in (("keogram", files["keograms"]), ("startrail", files["startrails"]), ("timelapse", files["timelapses"])):
        for path in paths:
            product_id = import_product(path, job["id"], product_type)
            imported_products.append(product_id)
            import_log.append({"kind": product_type, "id": product_id, "original_path": str(path)})
            completed_steps += 1
            update_allsky_import_progress(job["id"], completed_steps, total_steps)
    settings_result = apply_allsky_settings(root, job["id"])
    completed_steps += 1
    update_allsky_import_progress(job["id"], completed_steps, total_steps)
    with session() as conn:
        event(conn, "allsky_import_completed", {"job_id": job["id"], "images": len(imported_images), "dark_frames": len(imported_dark_frames), "products": len(imported_products)})
    return {
        "migration_job_id": job["id"],
        "imported_images": len(imported_images),
        "imported_dark_frames": len(imported_dark_frames),
        "imported_products": len(imported_products),
        "image_ids": imported_images,
        "dark_frame_ids": imported_dark_frames,
        "product_ids": imported_products,
        "import_log": import_log,
        "settings": settings_result,
        "unsupported_settings": preview_settings(root)["unsupported_settings"],
        "will_delete_original": False,
    }


def update_allsky_import_progress(job_id: str, completed_steps: int, total_steps: int) -> None:
    progress = 0.05 + (max(0, min(completed_steps, total_steps)) / max(1, total_steps)) * 0.85
    with session() as conn:
        conn.execute("UPDATE processing_jobs SET progress=? WHERE id=?", (max(0.05, min(0.95, progress)), job_id))


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


def import_dark_frame(source: Path, job_id: str) -> str:
    settings = get_settings()
    captured_at = datetime.fromtimestamp(source.stat().st_mtime, UTC)
    day_key = infer_day_key(source, captured_at)
    frame_id = new_id()
    suffix = normalized_image_suffix(source)
    target = settings.data_dir / "dark-frames" / day_key / f"allsky_dark_{captured_at.strftime('%H%M%S')}_{frame_id[:8]}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    thumbnail = make_thumbnail(target, settings.thumbnail_dir / "dark-frames" / day_key / target.name)
    width = height = None
    image_format = suffix.lstrip(".")
    try:
        with Image.open(target) as img:
            width, height = img.width, img.height
            image_format = (img.format or image_format).lower()
    except Exception:
        pass
    metadata = {
        "id": frame_id,
        "captured_at": captured_at.isoformat(),
        "storage": extract_image_metadata(target),
        "migration": {"source": "allsky", "job_id": job_id, "original_path": str(source)},
    }
    with session() as conn:
        conn.execute(
            """INSERT INTO dark_frames
               (id, camera_id, captured_at, day_key, file_path, thumbnail_path, format, width, height, size_bytes, metadata, created_at)
               VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                frame_id,
                captured_at.isoformat(),
                day_key,
                str(target),
                str(thumbnail) if thumbnail else None,
                image_format,
                width,
                height,
                target.stat().st_size,
                json_dumps(metadata),
                now_iso(),
            ),
        )
        event(conn, "allsky_dark_frame_imported", {"job_id": job_id, "dark_frame_id": frame_id, "original_path": str(source)})
    return frame_id


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
        dark_frames = [
            decode_row(row_to_dict(row))
            for row in conn.execute("SELECT * FROM dark_frames ORDER BY created_at DESC").fetchall()
        ]
        images = [image for image in images if migration_job_id(image) == job_id]
        products = [product for product in products if migration_job_id(product) == job_id]
        dark_frames = [frame for frame in dark_frames if migration_job_id(frame) == job_id]
        deleted_files: list[str] = []
        missing_files: list[str] = []
        skipped_files: list[dict[str, Any]] = []
        image_ids: list[str] = []
        product_ids: list[str] = []
        dark_frame_ids: list[str] = []
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
        for frame in dark_frames:
            result = delete_storage_paths(dark_frame_storage_artifacts(frame))
            conn.execute("DELETE FROM dark_frames WHERE id=?", (frame["id"],))
            dark_frame_ids.append(frame["id"])
            deleted_files.extend(result["deleted_files"])
            missing_files.extend(result["missing_files"])
            skipped_files.extend(result["skipped_files"])
        event(conn, "allsky_import_rolled_back", {"job_id": job_id, "images": len(image_ids), "dark_frames": len(dark_frame_ids), "products": len(product_ids)})
    return {
        "migration_job_id": job_id,
        "deleted_images": len(image_ids),
        "deleted_dark_frames": len(dark_frame_ids),
        "deleted_products": len(product_ids),
        "deleted_image_ids": image_ids,
        "deleted_dark_frame_ids": dark_frame_ids,
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
    overlay_enabled = first_bool(lookup, ("overlay", "overlay_enabled", "show_overlay", "show_text", "image_text_enabled"))
    overlay_lines = overlay_text_lines(lookup)
    overlay_font_size = first_float(lookup, ("font_size", "fontsize", "font"))
    overlay_text_color = first_text(lookup, ("text_color", "textcolor", "font_color", "fontcolor"))
    overlay_background_color = first_text(lookup, ("background_color", "backgroundcolor"))
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
    overlay: dict[str, Any] = {}
    if overlay_enabled is not None:
        overlay["enabled"] = overlay_enabled
    if overlay_lines:
        overlay["settings"] = {"lines": overlay_lines}
    if overlay_font_size is not None:
        overlay.setdefault("settings", {})["font_size"] = int(max(8, min(96, overlay_font_size)))
    if overlay_text_color:
        overlay.setdefault("settings", {})["text_color"] = normalize_color(overlay_text_color, "#ffffffff")
    if overlay_background_color:
        overlay.setdefault("settings", {})["background_color"] = normalize_color(overlay_background_color, "#00000099")
    if overlay:
        mapped["overlay"] = overlay
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
        overlay_row = row_to_dict(conn.execute("SELECT * FROM plugin_modules WHERE id=?", (OVERLAY_MODULE_ID,)).fetchone())
        backup["overlay_module"] = decode_row(overlay_row) if overlay_row else None

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
        if "overlay" in mapped:
            overlay_patch = mapped["overlay"]
            current_settings = {}
            current_enabled = 0
            if isinstance(backup.get("overlay_module"), dict):
                current_settings = backup["overlay_module"].get("settings") if isinstance(backup["overlay_module"].get("settings"), dict) else {}
                current_enabled = int(bool(backup["overlay_module"].get("enabled")))
            next_settings = merge_overlay_settings({**current_settings, **overlay_patch.get("settings", {})})
            next_enabled = int(bool(overlay_patch.get("enabled", current_enabled)))
            conn.execute(
                "UPDATE plugin_modules SET enabled=?, settings=?, updated_at=? WHERE id=?",
                (next_enabled, json_dumps(next_settings), now_iso(), OVERLAY_MODULE_ID),
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
    overlay_module = backup.get("overlay_module")
    if isinstance(overlay_module, dict) and overlay_module.get("id"):
        conn.execute(
            """UPDATE plugin_modules SET enabled=?, settings=?, updated_at=? WHERE id=?""",
            (int(bool(overlay_module.get("enabled"))), json_dumps(overlay_module.get("settings") or {}), now_iso(), overlay_module["id"]),
        )
        restored.append("overlay_module")
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


def dark_frame_storage_artifacts(frame: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for key in ("file_path", "thumbnail_path"):
        value = frame.get(key)
        if value:
            paths.append(Path(str(value)))
    return paths


def is_dark_frame_path(path: Path) -> bool:
    tokens = {part.lower().replace("-", "_") for part in path.parts[-5:]}
    name = path.name.lower().replace("-", "_")
    return (
        "dark" in tokens
        or "darks" in tokens
        or "dark_frames" in tokens
        or "darkframes" in tokens
        or name.startswith("dark_")
        or "darkframe" in name
        or "dark_frame" in name
    )


def normalized_parts(path: Path) -> set[str]:
    return {part.lower().replace("-", "_") for part in path.parts}


def is_excluded_import_path(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    parts = normalized_parts(relative)
    return bool(parts & EXCLUDED_IMPORT_PARTS)


def is_allsky_capture_path(path: Path) -> bool:
    parts = normalized_parts(path)
    name = path.name.lower()
    if not (parts & CAPTURE_DIR_PARTS):
        return False
    if any(token in name for token in ("keogram", "startrail", "dark", "thumbnail", "loading", "logo", "favicon")):
        return False
    return True


def is_allsky_product_path(path: Path, product_type: str) -> bool:
    parts = normalized_parts(path)
    name = path.name.lower()
    if product_type == "timelapse":
        return bool(parts & PRODUCT_DIR_PARTS) and "timelapse" in " ".join((*parts, name))
    return bool(parts & PRODUCT_DIR_PARTS) or product_type in name


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


def overlay_text_lines(values: dict[str, Any]) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    for index in range(1, 5):
        text = first_text(values, (f"overlayline{index}", f"textline{index}", f"line{index}"))
        if text:
            lines.append({"text": text[:240], "position": "bottom_left" if index == 1 else "bottom_right"})
    image_text = first_text(values, ("imagetext",))
    if image_text and not lines:
        lines.append({"text": image_text[:240], "position": "bottom_left"})
    return lines[:8]


def normalize_color(value: str, fallback: str) -> str:
    text = value.strip().lstrip("#")
    if len(text) in {6, 8} and all(char in "0123456789abcdefABCDEF" for char in text):
        if len(text) == 6:
            text += "ff"
        return f"#{text.lower()}"
    return fallback
