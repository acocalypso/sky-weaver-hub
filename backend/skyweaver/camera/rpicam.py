import asyncio
import shutil
from pathlib import Path

from .base import CameraAdapter, CameraCapabilities, CameraInfo, CaptureRequest, CaptureResult, DetectedCamera


class RpiCamAdapter(CameraAdapter):
    id = "rpicam"
    name = "Raspberry Pi libcamera/rpicam"
    backend = "rpicam"

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
        lines = [line.strip() for line in text.splitlines() if line.strip() and ")" in line]
        cameras: list[DetectedCamera] = []
        for index, line in enumerate(lines):
            cameras.append(DetectedCamera(id=f"rpicam://{index}", name=f"Pi camera {index}", backend=self.backend, model=line, metadata={"raw": line}))
        return cameras

    async def connect(self, camera_id: str) -> CameraInfo:
        return CameraInfo(id=camera_id, name="Raspberry Pi camera", backend=self.backend)

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
        ]
        if request.width:
            args += ["--width", str(request.width)]
        if request.height:
            args += ["--height", str(request.height)]
        if request.settings.get("tuning_file"):
            args += ["--tuning-file", str(request.settings["tuning_file"])]
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError((stderr or stdout).decode(errors="replace")[:2000])
        return CaptureResult(
            file_path=path,
            format=request.image_format.lower(),
            size_bytes=path.stat().st_size,
            exposure_ms=request.exposure_ms,
            gain=request.gain,
            metadata={"adapter": self.backend, "command": Path(still).name},
        )
