from .base import CameraAdapter
from .mock import MockCameraAdapter
from .rpicam import RpiCamAdapter


class NotInstalledAdapter(MockCameraAdapter):
    def __init__(self, adapter_id: str, label: str, hint: str) -> None:
        self.id = adapter_id
        self.backend = adapter_id
        self.name = label
        self.hint = hint

    async def detect(self):
        return []

    async def capture(self, request):
        raise RuntimeError(self.hint)


def adapters() -> dict[str, CameraAdapter]:
    return {
        "mock": MockCameraAdapter(),
        "rpicam": RpiCamAdapter(),
        "libcamera": RpiCamAdapter(),
        "zwo": NotInstalledAdapter("zwo", "ZWO ASI", "Install the ZWO SDK and enable the Sky Weaver ZWO adapter."),
        "gphoto2": NotInstalledAdapter("gphoto2", "gPhoto2 DSLR", "Install gphoto2; capture support is planned after Phase 1."),
        "v4l2": NotInstalledAdapter("v4l2", "V4L2 webcam", "Install v4l-utils/ffmpeg; capture support is planned after Phase 1."),
        "webcam": NotInstalledAdapter("webcam", "USB webcam", "Install v4l-utils/ffmpeg; capture support is planned after Phase 1."),
        "indi": NotInstalledAdapter("indi", "INDI camera", "Install INDI server/client libraries; adapter is a future extension point."),
        "custom_command": NotInstalledAdapter("custom_command", "Custom command", "Custom commands are disabled until sandboxing is configured."),
    }


def get_adapter(name: str) -> CameraAdapter:
    registry = adapters()
    if name not in registry:
        raise KeyError(f"Unknown camera adapter: {name}")
    return registry[name]
