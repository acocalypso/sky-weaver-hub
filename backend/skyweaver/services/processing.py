import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

from ..config import get_settings
from ..db import event, json_dumps, log, now_iso, row_to_dict, session
from .allsky_migration import execute_allsky_import
from .capture import decode_row, delete_storage_paths, make_thumbnail, processing_settings
from .uploads import execute_upload_processing_job


def update_worker_heartbeat(pid: int | None = None) -> None:
    ts = now_iso()
    with session() as conn:
        conn.execute("INSERT OR IGNORE INTO worker_state (id, updated_at) VALUES (1, ?)", (ts,))
        conn.execute(
            "UPDATE worker_state SET heartbeat_at=?, pid=?, updated_at=? WHERE id=1",
            (ts, pid if pid is not None else os.getpid(), ts),
        )


def record_worker_claimed(job: dict[str, Any]) -> None:
    ts = now_iso()
    with session() as conn:
        conn.execute("INSERT OR IGNORE INTO worker_state (id, updated_at) VALUES (1, ?)", (ts,))
        conn.execute(
            """UPDATE worker_state
               SET last_claimed_job_id=?, last_claimed_job_type=?, last_claimed_at=?, updated_at=?
               WHERE id=1""",
            (job["id"], job["type"], ts, ts),
        )


def record_worker_success() -> None:
    ts = now_iso()
    with session() as conn:
        conn.execute("INSERT OR IGNORE INTO worker_state (id, updated_at) VALUES (1, ?)", (ts,))
        conn.execute("UPDATE worker_state SET last_success_at=?, updated_at=? WHERE id=1", (ts, ts))


def claim_next_processing_job(job_types: tuple[str, ...] = ("thumbnail", "keogram", "timelapse", "mini_timelapse", "startrail", "upload", "allsky_import")) -> dict[str, Any] | None:
    placeholders = ",".join("?" for _ in job_types)
    with session() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            f"SELECT * FROM processing_jobs WHERE status='pending' AND type IN ({placeholders}) ORDER BY created_at LIMIT 1",
            job_types,
        ).fetchone()
        if not row:
            return None
        detail = {"progress_detail": {"stage": "starting", "message": "Worker claimed job"}}
        conn.execute("UPDATE processing_jobs SET status='running', progress=0.05, output=?, started_at=? WHERE id=?", (json_dumps(detail), now_iso(), row["id"]))
        event(conn, "processing_job_started", {"job_id": row["id"], "type": row["type"]})
        job = decode_row(row_to_dict(row))
        if job is None:
            raise RuntimeError("Claimed processing job disappeared")
    record_worker_claimed(job)
    return job


async def execute_processing_job(job: dict[str, Any]) -> dict[str, Any]:
    try:
        if job["type"] == "thumbnail":
            result = regenerate_thumbnail(job)
        elif job["type"] == "keogram":
            result = generate_keogram(job)
        elif job["type"] == "timelapse":
            result = generate_timelapse(job)
        elif job["type"] == "mini_timelapse":
            result = generate_timelapse(job, mini=True)
        elif job["type"] == "startrail":
            result = generate_startrail(job)
        elif job["type"] == "upload":
            result = execute_upload_processing_job(job)
        elif job["type"] == "allsky_import":
            result = execute_allsky_import(job)
        else:
            raise ValueError(f"Unsupported processing job type: {job['type']}")

        with session() as conn:
            conn.execute(
                "UPDATE processing_jobs SET status='completed', progress=1, output=?, completed_at=? WHERE id=?",
                (json_dumps(result), now_iso(), job["id"]),
            )
            event(conn, "processing_job_completed", {"job_id": job["id"], "type": job["type"], **result})
        return result
    except Exception as exc:
        with session() as conn:
            conn.execute("UPDATE processing_jobs SET status='failed', output=NULL, error=?, completed_at=? WHERE id=?", (str(exc), now_iso(), job["id"]))
            log(conn, "error", "worker", "Processing job failed", {"job_id": job["id"], "type": job["type"], "error": str(exc)})
            event(conn, "processing_job_failed", {"job_id": job["id"], "type": job["type"], "error": str(exc)})
        raise


def regenerate_thumbnail(job: dict[str, Any]) -> dict[str, Any]:
    image_id = job["input"].get("image_id")
    if not image_id:
        raise ValueError("thumbnail job requires image_id")

    settings = get_settings()
    with session() as conn:
        row = conn.execute("SELECT * FROM images WHERE id=?", (image_id,)).fetchone()
        image = decode_row(row_to_dict(row))
    if not image:
        raise LookupError("Image not found")

    source = Path(image["file_path"])
    if not source.exists():
        raise FileNotFoundError(source)

    target = settings.thumbnail_dir / image["day_key"] / source.name
    update_processing_progress(job["id"], 0.35, stage="thumbnail", message="Generating thumbnail", current=1, total=1)
    thumb = make_thumbnail(source, target)
    with session() as conn:
        conn.execute("UPDATE images SET thumbnail_path=? WHERE id=?", (str(thumb) if thumb else None, image_id))
    return {"image_id": image_id, "thumbnail_path": str(thumb) if thumb else None, "progress_detail": completed_progress_detail("thumbnail", 1, 1)}


def generate_keogram(job: dict[str, Any]) -> dict[str, Any]:
    day_key = job["input"].get("day_key")
    if not day_key:
        day_key = latest_day_key()
    if not day_key:
        raise ValueError("keogram job requires day_key or at least one image")

    images, source_count, skipped_bad_images = product_images_for_day(day_key, job)
    if not images:
        raise ValueError(no_usable_images_message(day_key, source_count, skipped_bad_images))

    settings = get_settings()
    product_dir = settings.product_dir / day_key
    product_dir.mkdir(parents=True, exist_ok=True)
    product_id = job["id"]
    output = product_dir / f"keogram_{day_key}_{product_id[:8]}.jpg"

    height = int(job["input"].get("height", 360))
    columns: list[Image.Image] = []
    for index, image in enumerate(images):
        with Image.open(image["file_path"]) as img:
            frame = img.convert("RGB")
            scale = height / frame.height
            width = max(1, int(frame.width * scale))
            frame = frame.resize((width, height))
            center = frame.width // 2
            columns.append(frame.crop((center, 0, center + 1, height)))
        update_processing_progress(product_id, 0.05 + ((index + 1) / len(images)) * 0.65, stage="frames", message="Extracting center columns", current=index + 1, total=len(images))

    update_processing_progress(product_id, 0.78, stage="compose", message="Composing keogram", current=len(columns), total=len(columns))
    keogram = Image.new("RGB", (len(columns), height))
    for x, column in enumerate(columns):
        keogram.paste(column, (x, 0))
    keogram = keogram.resize((max(360, len(columns)), height))
    update_processing_progress(product_id, 0.9, stage="write", message="Writing keogram image", current=len(columns), total=len(columns))
    keogram.save(output, quality=92)

    thumb = make_thumbnail(output, settings.thumbnail_dir / day_key / output.name)
    metadata = {"day_key": day_key, "source_images": source_count, "used_images": len(images), "skipped_bad_images": skipped_bad_images, "kind": "center-column"}
    with session() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO night_products (id, type, day_key, file_path, thumbnail_path, status, metadata, created_at) VALUES (?, 'keogram', ?, ?, ?, 'completed', ?, ?)",
            (product_id, day_key, str(output), str(thumb) if thumb else None, json_dumps(metadata), now_iso()),
        )
    return {"product_id": product_id, "day_key": day_key, "file_path": str(output), "thumbnail_path": str(thumb) if thumb else None, "source_images": source_count, "used_images": len(images), "skipped_bad_images": skipped_bad_images, "progress_detail": completed_progress_detail("keogram", len(images), len(images))}


def generate_startrail(job: dict[str, Any]) -> dict[str, Any]:
    day_key = job["input"].get("day_key") or latest_day_key()
    if not day_key:
        raise ValueError("startrail job requires day_key or at least one image")

    images, source_count, skipped_bad_images = product_images_for_day(day_key, job)
    if not images:
        raise ValueError(no_usable_images_message(day_key, source_count, skipped_bad_images))

    settings = get_settings()
    product_dir = settings.product_dir / day_key
    product_dir.mkdir(parents=True, exist_ok=True)
    product_id = job["id"]
    output = product_dir / f"startrail_{day_key}_{product_id[:8]}.jpg"
    max_width = max(320, min(3840, int(job["input"].get("max_width", 1920))))

    trail: Image.Image | None = None
    for index, image in enumerate(images):
        with Image.open(image["file_path"]) as img:
            frame = normalize_still_frame(img.convert("RGB"), max_width)
        if trail is None:
            trail = frame
        else:
            if frame.size != trail.size:
                frame = frame.resize(trail.size)
            trail = ImageChops.lighter(trail, frame)
        update_processing_progress(product_id, 0.05 + ((index + 1) / len(images)) * 0.8, stage="blend", message="Blending startrail frames", current=index + 1, total=len(images))

    if trail is None:
        raise ValueError(f"No readable images found for day {day_key}")
    update_processing_progress(product_id, 0.9, stage="write", message="Writing startrail image", current=len(images), total=len(images))
    trail.save(output, quality=94)
    thumb = make_thumbnail(output, settings.thumbnail_dir / day_key / output.name)
    metadata = {"day_key": day_key, "source_images": source_count, "used_images": len(images), "skipped_bad_images": skipped_bad_images, "kind": "lighten-blend", "max_width": max_width}
    with session() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO night_products (id, type, day_key, file_path, thumbnail_path, status, metadata, created_at) VALUES (?, 'startrail', ?, ?, ?, 'completed', ?, ?)",
            (product_id, day_key, str(output), str(thumb) if thumb else None, json_dumps(metadata), now_iso()),
        )
    return {"product_id": product_id, "day_key": day_key, "file_path": str(output), "thumbnail_path": str(thumb) if thumb else None, "source_images": source_count, "used_images": len(images), "skipped_bad_images": skipped_bad_images, "progress_detail": completed_progress_detail("startrail", len(images), len(images))}


def generate_timelapse(job: dict[str, Any], mini: bool = False) -> dict[str, Any]:
    day_key = job["input"].get("day_key") or latest_day_key()
    if not day_key:
        raise ValueError(f"{job['type']} job requires day_key or at least one image")

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to generate timelapse products")

    images, source_count, skipped_bad_images = product_images_for_day(day_key, job)
    if not images:
        raise ValueError(no_usable_images_message(day_key, source_count, skipped_bad_images))
    if mini:
        max_frames = max(1, min(300, int(job["input"].get("max_frames", 60))))
        images = sample_evenly(images, max_frames)

    settings = get_settings()
    product_dir = settings.product_dir / day_key
    product_dir.mkdir(parents=True, exist_ok=True)
    product_id = job["id"]
    fps = max(1, min(120, int(job["input"].get("fps", 15 if mini else 30))))
    max_width = max(160, min(3840, int(job["input"].get("max_width", 640 if mini else 1280))))
    codec = str(job["input"].get("codec", "h264")).lower()
    extension = "webm" if codec in {"vp9", "webm"} else "mp4"
    product_type = "mini_timelapse" if mini else "timelapse"
    output = product_dir / f"{product_type}_{day_key}_{product_id[:8]}.{extension}"
    frame_dir = product_dir / f".timelapse_frames_{product_id[:8]}"

    if frame_dir.exists():
        shutil.rmtree(frame_dir)
    frame_dir.mkdir(parents=True)

    try:
        for index, image in enumerate(images):
            with Image.open(image["file_path"]) as img:
                frame = normalize_video_frame(img.convert("RGB"), max_width)
                frame.save(frame_dir / f"frame_{index:06d}.jpg", quality=92)
            update_processing_progress(product_id, 0.05 + ((index + 1) / len(images)) * 0.65, stage="frames", message="Preparing video frames", current=index + 1, total=len(images))

        cmd = ffmpeg_command(ffmpeg, frame_dir / "frame_%06d.jpg", output, fps, codec)
        update_processing_progress(product_id, 0.82, stage="encode", message="Encoding video with ffmpeg", current=len(images), total=len(images))
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {completed.stderr.strip() or completed.stdout.strip()}")
        update_processing_progress(product_id, 0.9, stage="thumbnail", message="Generating product thumbnail", current=len(images), total=len(images))

        thumb = make_thumbnail(Path(images[0]["file_path"]), settings.thumbnail_dir / day_key / f"{output.stem}.jpg")
        metadata = {"day_key": day_key, "source_images": source_count, "used_images": len(images), "skipped_bad_images": skipped_bad_images, "fps": fps, "codec": codec, "format": extension, "mini": mini}
        with session() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO night_products (id, type, day_key, file_path, thumbnail_path, status, metadata, created_at) VALUES (?, ?, ?, ?, ?, 'completed', ?, ?)",
                (product_id, product_type, day_key, str(output), str(thumb) if thumb else None, json_dumps(metadata), now_iso()),
            )
        return {"product_id": product_id, "day_key": day_key, "file_path": str(output), "thumbnail_path": str(thumb) if thumb else None, "source_images": source_count, "used_images": len(images), "skipped_bad_images": skipped_bad_images, "progress_detail": completed_progress_detail(product_type, len(images), len(images))}
    finally:
        shutil.rmtree(frame_dir, ignore_errors=True)


def normalize_video_frame(frame: Image.Image, max_width: int) -> Image.Image:
    if frame.width > max_width:
        scale = max_width / frame.width
        frame = frame.resize((max_width, max(1, int(frame.height * scale))))
    if frame.width < 2 or frame.height < 2:
        frame = frame.resize((max(2, frame.width), max(2, frame.height)))
    width = frame.width - (frame.width % 2)
    height = frame.height - (frame.height % 2)
    if width != frame.width or height != frame.height:
        frame = frame.crop((0, 0, width, height))
    return frame


def sample_evenly(items: list[dict[str, Any]], max_items: int) -> list[dict[str, Any]]:
    if len(items) <= max_items:
        return items
    if max_items == 1:
        return [items[0]]
    last = len(items) - 1
    indexes = sorted({round(index * last / (max_items - 1)) for index in range(max_items)})
    return [items[index] for index in indexes]


def product_images_for_day(day_key: str, job: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int]:
    with session() as conn:
        rows = [
            decode_row(row_to_dict(row))
            for row in conn.execute("SELECT * FROM images WHERE day_key=? ORDER BY captured_at", (day_key,)).fetchall()
        ]
    existing = [image for image in rows if image and Path(image["file_path"]).exists()]
    source_count = len(existing)
    if not product_should_skip_bad_images(job):
        return existing, source_count, 0
    usable = [image for image in existing if not bool(image.get("bad_image"))]
    return usable, source_count, source_count - len(usable)


def product_should_skip_bad_images(job: dict[str, Any]) -> bool:
    if "skip_bad_images" in job.get("input", {}):
        return bool(job["input"]["skip_bad_images"])
    return bool(processing_settings().get("skip_bad_images", True))


def no_usable_images_message(day_key: str, source_count: int, skipped_bad_images: int) -> str:
    if source_count and skipped_bad_images == source_count:
        return f"No usable images found for day {day_key}; skipped {skipped_bad_images} bad image(s)"
    return f"No images found for day {day_key}"


def normalize_still_frame(frame: Image.Image, max_width: int) -> Image.Image:
    if frame.width <= max_width:
        return frame
    scale = max_width / frame.width
    return frame.resize((max_width, max(1, int(frame.height * scale))))


def ffmpeg_command(ffmpeg: str, input_pattern: Path, output: Path, fps: int, codec: str) -> list[str]:
    if codec in {"vp9", "webm"}:
        return [ffmpeg, "-y", "-framerate", str(fps), "-i", str(input_pattern), "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", str(output)]
    return [ffmpeg, "-y", "-framerate", str(fps), "-i", str(input_pattern), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]


def update_processing_progress(job_id: str, progress: float, *, stage: str | None = None, message: str | None = None, current: int | None = None, total: int | None = None) -> None:
    detail = None
    if stage or message or current is not None or total is not None:
        detail = {
            "progress_detail": {
                "stage": stage,
                "message": message,
                "current": current,
                "total": total,
            }
        }
    with session() as conn:
        if detail is None:
            conn.execute("UPDATE processing_jobs SET progress=? WHERE id=?", (max(0, min(1, progress)), job_id))
        else:
            conn.execute("UPDATE processing_jobs SET progress=?, output=? WHERE id=?", (max(0, min(1, progress)), json_dumps(detail), job_id))


def completed_progress_detail(stage: str, current: int, total: int) -> dict[str, Any]:
    return {"stage": stage, "message": "Completed", "current": current, "total": total}


def latest_day_key() -> str | None:
    with session() as conn:
        row = conn.execute("SELECT day_key FROM images ORDER BY captured_at DESC LIMIT 1").fetchone()
    return row["day_key"] if row else None


def product_storage_artifacts(product: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for key in ("file_path", "thumbnail_path"):
        value = product.get(key)
        if value:
            paths.append(Path(str(value)))
    return paths


def delete_product_files(product: dict[str, Any]) -> dict[str, Any]:
    return delete_storage_paths(product_storage_artifacts(product))


def cleanup_products_by_retention(conn, retention_days: int) -> dict[str, Any]:
    days = max(0, int(retention_days))
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = [
        decode_row(row_to_dict(row))
        for row in conn.execute("SELECT * FROM night_products WHERE created_at < ? ORDER BY created_at", (cutoff.isoformat(),)).fetchall()
    ]
    deleted_ids: list[str] = []
    deleted_files: list[str] = []
    missing_files: list[str] = []
    skipped_files: list[dict[str, Any]] = []
    for product in rows:
        file_result = delete_product_files(product)
        conn.execute("DELETE FROM night_products WHERE id=?", (product["id"],))
        deleted_ids.append(product["id"])
        deleted_files.extend(file_result["deleted_files"])
        missing_files.extend(file_result["missing_files"])
        skipped_files.extend(file_result["skipped_files"])
    return {
        "retention_days": days,
        "cutoff": cutoff.isoformat(),
        "deleted_products": len(deleted_ids),
        "deleted_product_ids": deleted_ids,
        "deleted_files": deleted_files,
        "missing_files": missing_files,
        "skipped_files": skipped_files,
    }


async def run_once() -> bool:
    update_worker_heartbeat()
    job = claim_next_processing_job()
    if not job:
        return False
    await execute_processing_job(job)
    record_worker_success()
    return True
