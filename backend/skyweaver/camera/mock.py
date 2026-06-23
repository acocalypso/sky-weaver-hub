import random
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .base import CameraAdapter, CameraCapabilities, CameraInfo, CaptureRequest, CaptureResult, DetectedCamera


class MockCameraAdapter(CameraAdapter):
    id = "mock"
    name = "Mock all-sky camera"
    backend = "mock"

    async def detect(self) -> list[DetectedCamera]:
        return [DetectedCamera(id="mock://default", name=self.name, backend=self.backend, model="Synthetic sky generator")]

    async def connect(self, camera_id: str) -> CameraInfo:
        return CameraInfo(id=camera_id, name=self.name, backend=self.backend, model="Synthetic sky generator")

    async def get_capabilities(self) -> CameraCapabilities:
        return CameraCapabilities(formats=["jpg", "png"], controls=["exposure_ms", "gain", "width", "height"], max_exposure_ms=60000)

    async def capture(self, request: CaptureRequest) -> CaptureResult:
        width = request.width or 1280
        height = request.height or 960
        path = request.output_path
        path.parent.mkdir(parents=True, exist_ok=True)

        img = Image.new("RGB", (width, height), (3, 7, 20))
        draw = ImageDraw.Draw(img)
        cx, cy = width // 2, height // 2
        radius = int(min(width, height) * 0.46)

        for y in range(height):
            shade = int(35 * (1 - y / max(height, 1)))
            draw.line([(0, y), (width, y)], fill=(3 + shade // 3, 8 + shade // 4, 22 + shade))

        for _ in range(550):
            angle = random.random() * 6.28318
            dist = radius * (random.random() ** 0.5)
            x = int(cx + dist * __import__("math").cos(angle))
            y = int(cy + dist * __import__("math").sin(angle))
            b = random.randint(145, 255)
            draw.point((x, y), fill=(b, b, min(255, b + 20)))

        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=(35, 120, 150), width=3)
        draw.text((24, 24), f"Sky Weaver mock {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}", fill=(180, 230, 255))
        img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120))

        fmt = "JPEG" if request.image_format.lower() in {"jpg", "jpeg"} else "PNG"
        img.save(path, fmt, quality=92)
        return CaptureResult(
            file_path=path,
            format=request.image_format.lower(),
            width=width,
            height=height,
            size_bytes=path.stat().st_size,
            exposure_ms=request.exposure_ms,
            gain=request.gain,
            temperature_c=32.0 + random.random() * 8,
            metadata={"adapter": self.backend, "synthetic": True},
        )
