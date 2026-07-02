import asyncio
from dataclasses import dataclass, field
import re
import shutil
import signal
from pathlib import Path

from .base import CameraAdapter, CameraCapabilities, CameraInfo, CaptureCancelResult, CaptureCanceled, CaptureRequest, CaptureResult, DetectedCamera


SIGUSR1 = getattr(signal, "SIGUSR1", None)


@dataclass
class RpiCamSession:
    key: tuple
    process: asyncio.subprocess.Process
    directory: Path
    pattern: Path
    next_index: int = 0
    log_tasks: list[asyncio.Task] = field(default_factory=list)


class RpiCamAdapter(CameraAdapter):
    id = "rpicam"
    name = "Raspberry Pi libcamera/rpicam"
    backend = "rpicam"
    supports_hard_cancel = True

    def __init__(self) -> None:
        self._active_processes: dict[str, tuple[asyncio.subprocess.Process, Path]] = {}
        self._canceled_jobs: set[str] = set()
        self._sessions: dict[tuple, RpiCamSession] = {}
        self._job_sessions: dict[str, tuple] = {}

    def _tools(self) -> tuple[str | None, str | None]:
        still = shutil.which("rpicam-still") or shutil.which("libcamera-still")
        hello = shutil.which("rpicam-hello") or shutil.which("libcamera-hello")
        return still, hello

    async def detect(self) -> list[DetectedCamera]:
        _still, hello = self._tools()
        if not hello:
            return []
        proc = await asyncio.create_subprocess_exec(
            hello, "--list-cameras",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        text = stdout.decode(errors="replace")
        if proc.returncode != 0 or "Available cameras" not in text:
            return []
        lines = [line.strip() for line in text.splitlines() if re.match(r"^\d+\s*:", line.strip())]
        cameras: list[DetectedCamera] = []
        for index, line in enumerate(lines):
            cameras.append(DetectedCamera(id=f"rpicam://{index}", name=f"Pi camera {index}", backend=self.backend, model=line, metadata={"raw": line}))
        return cameras

    async def connect(self, camera_id: str) -> CameraInfo:
        return CameraInfo(id=camera_id, name="Raspberry Pi camera", backend=self.backend)

    async def disconnect(self) -> None:
        for session in list(self._sessions.values()):
            await self._close_session(session)

    async def get_capabilities(self) -> CameraCapabilities:
        return CameraCapabilities(
            formats=["jpg", "png", "dng"],
            controls=["exposure_ms", "gain", "awb", "tuning_file", "width", "height", "quality"],
            max_exposure_ms=120000,
        )

    async def capture(self, request: CaptureRequest) -> CaptureResult:
        still, _hello = self._tools()
        if not still:
            raise RuntimeError("rpicam-still/libcamera-still was not found. Install rpicam-apps or libcamera-apps.")
        if self._persistent_allowed(request):
            return await self._capture_persistent(still, request)
        return await self._capture_once(still, request)

    def _persistent_allowed(self, request: CaptureRequest) -> bool:
        if request.settings.get("persistent") is False:
            return False
        if SIGUSR1 is None:
            return False
        return request.image_format.lower() in {"jpg", "jpeg", "png"}

    def _session_key(self, still: str, request: CaptureRequest) -> tuple:
        return (
            still,
            float(request.exposure_ms),
            float(request.gain),
            int(request.width or 0),
            int(request.height or 0),
            request.image_format.lower(),
            str(request.settings.get("tuning_file") or ""),
            str(request.settings.get("mode") or ""),
            str(request.settings.get("denoise") or ""),
            int(request.settings.get("quality", 0) or 0),
        )

    async def _session_for_request(self, still: str, request: CaptureRequest) -> RpiCamSession:
        key = self._session_key(still, request)
        existing = self._sessions.get(key)
        if existing and existing.process.returncode is None:
            return existing
        if existing:
            await self._close_session(existing)
        await self._close_incompatible_sessions(still, request)

        session_dir = request.output_path.parent / ".rpicam-session"
        session_dir.mkdir(parents=True, exist_ok=True)
        pattern = session_dir / "frame_%04d"
        suffix = ".jpg" if request.image_format.lower() in {"jpg", "jpeg"} else ".png"
        pattern = pattern.with_suffix(suffix)
        for stale in session_dir.glob(f"frame_*{suffix}"):
            stale.unlink(missing_ok=True)
        timeout_ms = int(request.settings.get("persistent_timeout_ms") or 12 * 60 * 60 * 1000)
        args = [
            still,
            "--signal",
            "--output",
            str(pattern),
            "--timeout",
            str(timeout_ms),
            "--shutter",
            str(int(request.exposure_ms * 1000)),
            "--gain",
            str(request.gain),
            "--nopreview",
            "--encoding",
            "jpg" if request.image_format.lower() in {"jpg", "jpeg"} else "png",
        ]
        if request.width:
            args += ["--width", str(request.width)]
        if request.height:
            args += ["--height", str(request.height)]
        if request.settings.get("tuning_file"):
            args += ["--tuning-file", str(request.settings["tuning_file"])]
        if request.settings.get("denoise"):
            args += ["--denoise", str(request.settings["denoise"])]
        if request.settings.get("quality") and request.image_format.lower() in {"jpg", "jpeg"}:
            args += ["--quality", str(int(request.settings["quality"]))]
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        session = RpiCamSession(key=key, process=proc, directory=session_dir, pattern=pattern)
        session.log_tasks = self._collect_session_output(proc)
        self._sessions[key] = session
        await asyncio.sleep(float(request.settings.get("persistent_warmup_seconds", 1.0)))
        if proc.returncode is not None:
            stderr = await self._process_output(proc)
            raise RuntimeError(stderr[:2000] or "rpicam persistent capture process exited during startup")
        return session

    def _collect_session_output(self, proc: asyncio.subprocess.Process) -> list[asyncio.Task]:
        tasks: list[asyncio.Task] = []
        for stream in (proc.stdout, proc.stderr):
            if stream is None:
                continue
            tasks.append(asyncio.create_task(self._read_stream(stream)))
        return tasks

    async def _read_stream(self, stream) -> None:
        try:
            await stream.read()
        except Exception:
            return

    async def _process_output(self, proc: asyncio.subprocess.Process) -> str:
        chunks: list[bytes] = []
        for stream in (proc.stdout, proc.stderr):
            if stream is None:
                continue
            try:
                chunks.append(await asyncio.wait_for(stream.read(), timeout=0.2))
            except (asyncio.TimeoutError, RuntimeError):
                continue
        return b"\n".join(chunks).decode(errors="replace")

    async def _close_incompatible_sessions(self, still: str, request: CaptureRequest) -> None:
        keep = self._session_key(still, request)
        for key, session in list(self._sessions.items()):
            if key != keep:
                await self._close_session(session)

    async def _close_session(self, session: RpiCamSession) -> None:
        self._sessions.pop(session.key, None)
        if session.process.returncode is None:
            session.process.terminate()
            try:
                await asyncio.wait_for(session.process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                session.process.kill()
                await session.process.wait()
        for task in session.log_tasks or []:
            task.cancel()

    def _session_output_path(self, session: RpiCamSession, index: int) -> Path:
        return Path(str(session.pattern).replace("%04d", f"{index:04d}"))

    async def _wait_for_session_file(self, session: RpiCamSession, index: int, request: CaptureRequest) -> Path:
        path = self._session_output_path(session, index)
        timeout_s = max(10.0, float(request.exposure_ms) / 1000.0 + 15.0)
        deadline = asyncio.get_running_loop().time() + timeout_s
        last_size = -1
        stable_seen = 0
        while asyncio.get_running_loop().time() < deadline:
            if session.process.returncode is not None:
                raise RuntimeError("rpicam persistent capture process exited before writing an image")
            if path.exists():
                size = path.stat().st_size
                if size > 0 and size == last_size:
                    stable_seen += 1
                    if stable_seen >= 2:
                        return path
                else:
                    stable_seen = 0
                    last_size = size
            await asyncio.sleep(0.2)
        raise TimeoutError(f"Timed out waiting for rpicam persistent capture output {path}")

    async def _capture_persistent(self, still: str, request: CaptureRequest) -> CaptureResult:
        sigusr1 = SIGUSR1
        if sigusr1 is None:
            raise RuntimeError("Persistent rpicam capture requires SIGUSR1 support on this platform.")
        session = await self._session_for_request(still, request)
        job_key = request.job_id or str(request.output_path)
        self._active_processes[job_key] = (session.process, request.output_path)
        self._job_sessions[job_key] = session.key
        target_index = session.next_index
        session.next_index += 1
        try:
            session.process.send_signal(sigusr1)
            try:
                source = await self._wait_for_session_file(session, target_index, request)
            except Exception:
                await self._close_session(session)
                raise
            request.output_path.parent.mkdir(parents=True, exist_ok=True)
            if request.output_path.exists():
                request.output_path.unlink()
            source.replace(request.output_path)
            if job_key in self._canceled_jobs:
                request.output_path.unlink(missing_ok=True)
                raise CaptureCanceled("Capture canceled by operator stop")
        finally:
            self._active_processes.pop(job_key, None)
            self._job_sessions.pop(job_key, None)
            self._canceled_jobs.discard(job_key)
        return CaptureResult(
            file_path=request.output_path,
            format=request.image_format.lower(),
            size_bytes=request.output_path.stat().st_size,
            exposure_ms=request.exposure_ms,
            gain=request.gain,
            metadata={"adapter": self.backend, "command": Path(still).name, "capture_mode": "persistent_signal"},
        )

    async def _capture_once(self, still: str, request: CaptureRequest) -> CaptureResult:
        path: Path = request.output_path
        path.parent.mkdir(parents=True, exist_ok=True)
        timeout_ms = max(1, int(request.exposure_ms + 500))
        args = [
            still,
            "--output", str(path),
            "--timeout", str(timeout_ms),
            "--shutter", str(int(request.exposure_ms * 1000)),
            "--gain", str(request.gain),
            "--immediate",
            "--nopreview",
        ]
        if request.width:
            args += ["--width", str(request.width)]
        if request.height:
            args += ["--height", str(request.height)]
        if request.settings.get("tuning_file"):
            args += ["--tuning-file", str(request.settings["tuning_file"])]
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        job_key = request.job_id or str(path)
        self._active_processes[job_key] = (proc, path)
        try:
            stdout, stderr = await proc.communicate()
            if job_key in self._canceled_jobs:
                path.unlink(missing_ok=True)
                raise CaptureCanceled("Capture canceled by operator stop")
            if proc.returncode != 0:
                raise RuntimeError((stderr or stdout).decode(errors="replace")[:2000])
        finally:
            self._active_processes.pop(job_key, None)
            self._canceled_jobs.discard(job_key)
        return CaptureResult(
            file_path=path,
            format=request.image_format.lower(),
            size_bytes=path.stat().st_size,
            exposure_ms=request.exposure_ms,
            gain=request.gain,
            metadata={"adapter": self.backend, "command": Path(still).name},
        )

    async def cancel_capture(self, job_id: str, reason: str = "operator stop") -> CaptureCancelResult:
        active = self._active_processes.get(job_id)
        if not active:
            return CaptureCancelResult(supported=True, canceled=False, method="process", message="No active rpicam subprocess for this job")
        proc, path = active
        self._canceled_jobs.add(job_id)
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                method = "kill"
            else:
                method = "terminate"
        else:
            method = "already-exited"
        session_key = self._job_sessions.pop(job_id, None)
        if session_key and session_key in self._sessions:
            self._sessions.pop(session_key, None)
        path.unlink(missing_ok=True)
        return CaptureCancelResult(supported=True, canceled=True, method=method, message=reason)
