import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from ..config import get_settings
from ..db import event, json_dumps, new_id, now_iso, row_to_dict, session
from .capture import analyze_image, decode_row, delete_image_files, delete_storage_paths, extract_image_metadata, make_thumbnail

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
VIDEO_SUFFIXES = {".mp4", ".webm"}
DATE_PATTERNS = (
    re.compile(r"(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)"),
    re.compile(r"([01]\d)[-_]?([0-3]\d)[-_]?(20\d{2})"),
)
CONFIG_NAMES = {"config.sh", "settings.json", "options.json", "camera_settings.json", "ftp-settings.sh", "ftp-settings.json"}


def preview_allsky_root(root: Path) -> dict[str, Any]:
    files = scan_allsky_files(root)
    unsupported = unsupported_settings(root)
    return {
        "path": str(root),
        "exists": root.exists(),
        "counts": {
            "images": len(files["images"]),
            "timelapses": len(files["timelapses"]),
            "keograms": len(files["keograms"]),
            "startrails": len(files["startrails"]),
        },
        "unsupported_settings": unsupported,
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
                "reason": "settings_translation_not_implemented",
            })
    return findings


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
    with session() as conn:
        event(conn, "allsky_import_completed", {"job_id": job["id"], "images": len(imported_images), "products": len(imported_products)})
    return {
        "migration_job_id": job["id"],
        "imported_images": len(imported_images),
        "imported_products": len(imported_products),
        "image_ids": imported_images,
        "product_ids": imported_products,
        "unsupported_settings": unsupported_settings(root),
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
    }


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
