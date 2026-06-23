import asyncio
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import get_settings
from .db import init_db, log, session
from .services.capture import (
    capture_interval_seconds,
    capture_is_running,
    claim_next_capture_job,
    create_capture_job,
    execute_capture,
    execute_capture_job,
    schedule_allows_capture,
    schedule_command,
    update_daemon_heartbeat,
)
from .services.recovery import recover_capture_jobs


class CaptureDaemon:
    def __init__(self) -> None:
        self.last_capture_monotonic: float | None = None

    async def run_once(self, force: bool = False) -> bool:
        update_daemon_heartbeat()
        if not capture_is_running():
            return False

        queued_job = claim_next_capture_job()
        if queued_job:
            await execute_capture_job(queued_job)
            if queued_job["type"] == "scheduled":
                self.last_capture_monotonic = time.monotonic()
            return True

        interval = capture_interval_seconds()
        now = time.monotonic()
        if not force and self.last_capture_monotonic is not None and now - self.last_capture_monotonic < interval:
            return False
        if not force and not schedule_allows_capture():
            return False

        command = schedule_command()
        with session() as conn:
            job_id = create_capture_job(conn, "scheduled", command.as_dict())
        await execute_capture(command, job_type="scheduled", job_id=job_id)
        self.last_capture_monotonic = time.monotonic()
        return True

    async def run_forever(self, poll_seconds: float = 1.0) -> None:
        with session() as conn:
            log(conn, "info", "capture-daemon", "Capture daemon loop started", {})
        while True:
            try:
                captured = await self.run_once()
                await asyncio.sleep(0 if captured else poll_seconds)
            except Exception as exc:
                with session() as conn:
                    log(conn, "error", "capture-daemon", "Scheduled capture failed", {"error": str(exc)})
                await asyncio.sleep(max(5.0, poll_seconds))


@contextmanager
def daemon_lock() -> Iterator[None]:
    settings = get_settings()
    lock_path = settings.data_dir / "capture-daemon.lock"
    fd: int | None = None
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("ascii"))
        yield
    except FileExistsError as exc:
        raise RuntimeError(f"Capture daemon lock already exists: {lock_path}") from exc
    finally:
        if fd is not None:
            os.close(fd)
            try:
                Path(lock_path).unlink()
            except FileNotFoundError:
                pass


async def main() -> None:
    init_db()
    recover_capture_jobs()
    with daemon_lock():
        await CaptureDaemon().run_forever()


if __name__ == "__main__":
    asyncio.run(main())
