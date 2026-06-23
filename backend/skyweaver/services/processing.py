import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image

from ..config import get_settings
from ..db import event, json_dumps, log, now_iso, row_to_dict, session
from .capture import decode_row, make_thumbnail


def claim_next_processing_job(job_types: tuple[str, ...] = ("thumbnail", "keogram", "timelapse")) -> dict[str, Any] | None:
    placeholders = ",".join("?" for _ in job_types)
    with session() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            f"SELECT * FROM processing_jobs WHERE status='pending' AND type IN ({placeholders}) ORDER BY created_at LIMIT 1",
            job_types,
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE processing_jobs SET status='running', progress=0.05, started_at=? WHERE id=?", (now_iso(), row["id"]))
        event(conn, "processing_job_started", {"job_id": row["id"], "type": row["type"]})
        return decode_row(row_to_dict(row))


async def execute_processing_job(job: dict[str, Any]) -> dict[str, Any]:
    try:
        if job["type"] == "thumbnail":
            result = regenerate_thumbnail(job)
        elif job["type"] == "keogram":
            result = generate_keogram(job)
        elif job["type"] == "timelapse":
            result = generate_timelapse(job)
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
            conn.execute("UPDATE processing_jobs SET status='failed', error=?, completed_at=? WHERE id=?", (str(exc), now_iso(), job["id"]))
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
    thumb = make_thumbnail(source, target)
    with session() as conn:
        conn.execute("UPDATE images SET thumbnail_path=? WHERE id=?", (str(thumb) if thumb else None, image_id))
    return {"image_id": image_id, "thumbnail_path": str(thumb) if thumb else None}


def generate_keogram(job: dict[str, Any]) -> dict[str, Any]:
    day_key = job["input"].get("day_key")
    if not day_key:
        day_key = latest_day_key()
    if not day_key:
        raise ValueError("keogram job requires day_key or at least one image")

    with session() as conn:
        images = [
            decode_row(row_to_dict(row))
            for row in conn.execute("SELECT * FROM images WHERE day_key=? ORDER BY captured_at", (day_key,)).fetchall()
        ]
    images = [image for image in images if image and Path(image["file_path"]).exists()]
    if not images:
        raise ValueError(f"No images found for day {day_key}")

    settings = get_settings()
    product_dir = settings.product_dir / day_key
    product_dir.mkdir(parents=True, exist_ok=True)
    product_id = job["id"]
    output = product_dir / f"keogram_{day_key}_{product_id[:8]}.jpg"

    height = int(job["input"].get("height", 360))
    columns: list[Image.Image] = []
    for image in images:
        with Image.open(image["file_path"]) as img:
            frame = img.convert("RGB")
            scale = height / frame.height
            width = max(1, int(frame.width * scale))
            frame = frame.resize((width, height))
            center = frame.width // 2
            columns.append(frame.crop((center, 0, center + 1, height)))

    keogram = Image.new("RGB", (len(columns), height))
    for x, column in enumerate(columns):
        keogram.paste(column, (x, 0))
    keogram = keogram.resize((max(360, len(columns)), height))
    keogram.save(output, quality=92)

    thumb = make_thumbnail(output, settings.thumbnail_dir / day_key / output.name)
    metadata = {"day_key": day_key, "source_images": len(images), "kind": "center-column"}
    with session() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO night_products (id, type, day_key, file_path, thumbnail_path, status, metadata, created_at) VALUES (?, 'keogram', ?, ?, ?, 'completed', ?, ?)",
            (product_id, day_key, str(output), str(thumb) if thumb else None, json_dumps(metadata), now_iso()),
        )
    return {"product_id": product_id, "day_key": day_key, "file_path": str(output), "thumbnail_path": str(thumb) if thumb else None, "source_images": len(images)}


def generate_timelapse(job: dict[str, Any]) -> dict[str, Any]:
    day_key = job["input"].get("day_key") or latest_day_key()
    if not day_key:
        raise ValueError("timelapse job requires day_key or at least one image")

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to generate timelapse products")

    with session() as conn:
        images = [
            decode_row(row_to_dict(row))
            for row in conn.execute("SELECT * FROM images WHERE day_key=? ORDER BY captured_at", (day_key,)).fetchall()
        ]
    images = [image for image in images if image and Path(image["file_path"]).exists()]
    if not images:
        raise ValueError(f"No images found for day {day_key}")

    settings = get_settings()
    product_dir = settings.product_dir / day_key
    product_dir.mkdir(parents=True, exist_ok=True)
    product_id = job["id"]
    fps = max(1, min(120, int(job["input"].get("fps", 30))))
    max_width = max(320, min(3840, int(job["input"].get("max_width", 1280))))
    codec = str(job["input"].get("codec", "h264")).lower()
    extension = "webm" if codec in {"vp9", "webm"} else "mp4"
    output = product_dir / f"timelapse_{day_key}_{product_id[:8]}.{extension}"
    frame_dir = product_dir / f".timelapse_frames_{product_id[:8]}"

    if frame_dir.exists():
        shutil.rmtree(frame_dir)
    frame_dir.mkdir(parents=True)

    try:
        for index, image in enumerate(images):
            with Image.open(image["file_path"]) as img:
                frame = normalize_video_frame(img.convert("RGB"), max_width)
                frame.save(frame_dir / f"frame_{index:06d}.jpg", quality=92)
            update_processing_progress(product_id, 0.05 + ((index + 1) / len(images)) * 0.65)

        cmd = ffmpeg_command(ffmpeg, frame_dir / "frame_%06d.jpg", output, fps, codec)
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {completed.stderr.strip() or completed.stdout.strip()}")
        update_processing_progress(product_id, 0.9)

        thumb = make_thumbnail(Path(images[0]["file_path"]), settings.thumbnail_dir / day_key / f"{output.stem}.jpg")
        metadata = {"day_key": day_key, "source_images": len(images), "fps": fps, "codec": codec, "format": extension}
        with session() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO night_products (id, type, day_key, file_path, thumbnail_path, status, metadata, created_at) VALUES (?, 'timelapse', ?, ?, ?, 'completed', ?, ?)",
                (product_id, day_key, str(output), str(thumb) if thumb else None, json_dumps(metadata), now_iso()),
            )
        return {"product_id": product_id, "day_key": day_key, "file_path": str(output), "thumbnail_path": str(thumb) if thumb else None, "source_images": len(images)}
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


def ffmpeg_command(ffmpeg: str, input_pattern: Path, output: Path, fps: int, codec: str) -> list[str]:
    if codec in {"vp9", "webm"}:
        return [ffmpeg, "-y", "-framerate", str(fps), "-i", str(input_pattern), "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", str(output)]
    return [ffmpeg, "-y", "-framerate", str(fps), "-i", str(input_pattern), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]


def update_processing_progress(job_id: str, progress: float) -> None:
    with session() as conn:
        conn.execute("UPDATE processing_jobs SET progress=? WHERE id=?", (max(0, min(1, progress)), job_id))


def latest_day_key() -> str | None:
    with session() as conn:
        row = conn.execute("SELECT day_key FROM images ORDER BY captured_at DESC LIMIT 1").fetchone()
    return row["day_key"] if row else None


async def run_once() -> bool:
    job = claim_next_processing_job()
    if not job:
        return False
    await execute_processing_job(job)
    return True
