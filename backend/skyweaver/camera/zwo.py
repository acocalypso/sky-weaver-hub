import asyncio
import ctypes
import ctypes.util
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from PIL import Image

from .base import CameraAdapter, CameraCapabilities, CameraInfo, CaptureCancelResult, CaptureCanceled, CaptureRequest, CaptureResult, DetectedCamera

ASI_SUCCESS = 0
ASI_IMG_RAW8 = 0
ASI_IMG_RGB24 = 1
ASI_IMG_RAW16 = 2
ASI_IMG_Y8 = 3
ASI_IMG_END = -1
ASI_GAIN = 0
ASI_EXPOSURE = 1
ASI_TEMPERATURE = 8
ASI_COOLER_ON = 17
ASI_TARGET_TEMP = 16
ASI_EXP_IDLE = 0
ASI_EXP_WORKING = 1
ASI_EXP_SUCCESS = 2
ASI_EXP_FAILED = 3
ZWO_CLI_CONFIG = "zwo_asi.toml"

ERROR_NAMES = {
    0: "ASI_SUCCESS",
    1: "ASI_ERROR_INVALID_INDEX",
    2: "ASI_ERROR_INVALID_ID",
    3: "ASI_ERROR_INVALID_CONTROL_TYPE",
    4: "ASI_ERROR_CAMERA_CLOSED",
    5: "ASI_ERROR_CAMERA_REMOVED",
    6: "ASI_ERROR_INVALID_PATH",
    7: "ASI_ERROR_INVALID_FILEFORMAT",
    8: "ASI_ERROR_INVALID_SIZE",
    9: "ASI_ERROR_INVALID_IMGTYPE",
    10: "ASI_ERROR_OUTOF_BOUNDARY",
    11: "ASI_ERROR_TIMEOUT",
    12: "ASI_ERROR_INVALID_SEQUENCE",
    13: "ASI_ERROR_BUFFER_TOO_SMALL",
    14: "ASI_ERROR_VIDEO_MODE_ACTIVE",
    15: "ASI_ERROR_EXPOSURE_IN_PROGRESS",
    16: "ASI_ERROR_GENERAL_ERROR",
    17: "ASI_ERROR_INVALID_MODE",
}


class ASICameraInfo(ctypes.Structure):
    _fields_ = [
        ("Name", ctypes.c_char * 64),
        ("CameraID", ctypes.c_int),
        ("MaxHeight", ctypes.c_long),
        ("MaxWidth", ctypes.c_long),
        ("IsColorCam", ctypes.c_int),
        ("BayerPattern", ctypes.c_int),
        ("SupportedBins", ctypes.c_int * 16),
        ("SupportedVideoFormat", ctypes.c_int * 8),
        ("PixelSize", ctypes.c_double),
        ("MechanicalShutter", ctypes.c_int),
        ("ST4Port", ctypes.c_int),
        ("IsCoolerCam", ctypes.c_int),
        ("IsUSB3Host", ctypes.c_int),
        ("IsUSB3Camera", ctypes.c_int),
        ("ElecPerADU", ctypes.c_float),
        ("BitDepth", ctypes.c_int),
        ("IsTriggerCam", ctypes.c_int),
        ("Unused", ctypes.c_char * 16),
    ]


class ZwoSdkError(RuntimeError):
    pass


class ZwoSdkUnavailable(ZwoSdkError):
    pass


def decode_c_string(value: bytes) -> str:
    return value.split(b"\0", 1)[0].decode(errors="replace")


def supported_ints(values) -> list[int]:
    items: list[int] = []
    for value in values:
        item = int(value)
        if item == ASI_IMG_END:
            break
        items.append(item)
    return items


def parse_zwo_print_output(text: str) -> list[DetectedCamera]:
    cameras: list[DetectedCamera] = []
    current_index: int | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        header = re.match(r"-+\s*camera\s+(\d+)\s*-+", line, re.IGNORECASE)
        if header:
            current_index = int(header.group(1))
            continue
        colon = re.match(r"(\d+)\s*:\s*(.+)", line)
        if colon:
            index = int(colon.group(1))
            name = colon.group(2).strip()
        else:
            info = re.match(r"(.+?)\s+\(id:\s*(\d+)\)", line, re.IGNORECASE)
            if not info:
                continue
            name = info.group(1).strip()
            index = current_index if current_index is not None else int(info.group(2))
        cameras.append(
            DetectedCamera(
                id=f"zwo://{index}",
                name=name,
                backend="zwo",
                model=name,
                serial=str(index),
                metadata={"cli": True},
            )
        )
        current_index = None
    return cameras


def toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def merge_toml_lines(existing: str, updates: dict[str, Any]) -> str:
    lines = existing.splitlines()
    found: set[str] = set()
    out: list[str] = []
    current_section = ""
    for line in lines:
        stripped = line.strip()
        section = re.match(r"^\[(.+)]$", stripped)
        if section:
            current_section = section.group(1).strip()
            out.append(line)
            continue
        replaced = False
        for key, value in updates.items():
            section_name, item_name = split_toml_key(key)
            if section_name == current_section and re.match(rf"^{re.escape(item_name)}\s*=", stripped):
                out.append(f"{item_name} = {toml_value(value)}")
                found.add(key)
                replaced = True
                break
        if not replaced:
            out.append(line)
    missing_by_section: dict[str, list[tuple[str, Any]]] = {}
    for key, value in updates.items():
        if key in found:
            continue
        section_name, item_name = split_toml_key(key)
        missing_by_section.setdefault(section_name, []).append((item_name, value))
    for section_name, items in missing_by_section.items():
        if out and out[-1].strip():
            out.append("")
        if section_name:
            out.append(f"[{section_name}]")
        for item_name, value in items:
            out.append(f"{item_name} = {toml_value(value)}")
    return "\n".join(out).rstrip() + "\n"


def split_toml_key(key: str) -> tuple[str, str]:
    if "." not in key:
        return "", key
    section, item = key.rsplit(".", 1)
    return section, item


class ZwoSdk:
    def __init__(self, library_path: str | None = None) -> None:
        self.library_path = library_path or self.find_library()
        if not self.library_path:
            raise ZwoSdkUnavailable("ZWO ASI SDK library not found. Install the ASI Camera SDK and make libASICamera2.so available in LD_LIBRARY_PATH, or set SKYWEAVER_ZWO_SDK_LIBRARY.")
        try:
            self.lib = ctypes.CDLL(self.library_path)
        except OSError as exc:
            raise ZwoSdkUnavailable(f"ZWO ASI SDK library could not be loaded from {self.library_path}: {exc}") from exc
        self._configure()

    @staticmethod
    def find_library() -> str | None:
        env_path = os.environ.get("SKYWEAVER_ZWO_SDK_LIBRARY")
        if env_path:
            return env_path
        found = ctypes.util.find_library("ASICamera2")
        if found:
            return found
        for name in ("libASICamera2.so", "ASICamera2.dll", "ASICamera2.dylib"):
            if Path(name).exists():
                return str(Path(name).resolve())
        return None

    def _configure(self) -> None:
        self.lib.ASIGetNumOfConnectedCameras.restype = ctypes.c_int
        self.lib.ASIGetCameraProperty.argtypes = [ctypes.POINTER(ASICameraInfo), ctypes.c_int]
        self.lib.ASIGetCameraProperty.restype = ctypes.c_int
        self.lib.ASIOpenCamera.argtypes = [ctypes.c_int]
        self.lib.ASIOpenCamera.restype = ctypes.c_int
        self.lib.ASIInitCamera.argtypes = [ctypes.c_int]
        self.lib.ASIInitCamera.restype = ctypes.c_int
        self.lib.ASICloseCamera.argtypes = [ctypes.c_int]
        self.lib.ASICloseCamera.restype = ctypes.c_int
        self.lib.ASISetControlValue.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_long, ctypes.c_int]
        self.lib.ASISetControlValue.restype = ctypes.c_int
        self.lib.ASIGetControlValue.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_long), ctypes.POINTER(ctypes.c_int)]
        self.lib.ASIGetControlValue.restype = ctypes.c_int
        self.lib.ASISetROIFormat.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self.lib.ASISetROIFormat.restype = ctypes.c_int
        self.lib.ASIStartExposure.argtypes = [ctypes.c_int, ctypes.c_int]
        self.lib.ASIStartExposure.restype = ctypes.c_int
        self.lib.ASIStopExposure.argtypes = [ctypes.c_int]
        self.lib.ASIStopExposure.restype = ctypes.c_int
        self.lib.ASIGetExpStatus.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        self.lib.ASIGetExpStatus.restype = ctypes.c_int
        self.lib.ASIGetDataAfterExp.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_ubyte), ctypes.c_long]
        self.lib.ASIGetDataAfterExp.restype = ctypes.c_int

    def check(self, code: int, operation: str) -> None:
        if code != ASI_SUCCESS:
            raise ZwoSdkError(f"{operation} failed: {ERROR_NAMES.get(code, f'ASI_ERROR_{code}')}")

    def camera_count(self) -> int:
        return int(self.lib.ASIGetNumOfConnectedCameras())

    def camera_property(self, index: int) -> ASICameraInfo:
        info = ASICameraInfo()
        self.check(self.lib.ASIGetCameraProperty(ctypes.byref(info), index), "ASIGetCameraProperty")
        return info

    def open(self, camera_id: int) -> None:
        self.check(self.lib.ASIOpenCamera(camera_id), "ASIOpenCamera")

    def init(self, camera_id: int) -> None:
        self.check(self.lib.ASIInitCamera(camera_id), "ASIInitCamera")

    def close(self, camera_id: int) -> None:
        self.lib.ASICloseCamera(camera_id)

    def set_control(self, camera_id: int, control_type: int, value: int) -> None:
        self.check(self.lib.ASISetControlValue(camera_id, control_type, int(value), 0), "ASISetControlValue")

    def get_control(self, camera_id: int, control_type: int) -> int | None:
        value = ctypes.c_long()
        auto = ctypes.c_int()
        code = self.lib.ASIGetControlValue(camera_id, control_type, ctypes.byref(value), ctypes.byref(auto))
        return int(value.value) if code == ASI_SUCCESS else None

    def set_roi(self, camera_id: int, width: int, height: int, image_type: int) -> None:
        self.check(self.lib.ASISetROIFormat(camera_id, width, height, 1, image_type), "ASISetROIFormat")

    def start_exposure(self, camera_id: int, dark: bool = False) -> None:
        self.check(self.lib.ASIStartExposure(camera_id, 1 if dark else 0), "ASIStartExposure")

    def stop_exposure(self, camera_id: int) -> None:
        self.lib.ASIStopExposure(camera_id)

    def exposure_status(self, camera_id: int) -> int:
        status = ctypes.c_int()
        self.check(self.lib.ASIGetExpStatus(camera_id, ctypes.byref(status)), "ASIGetExpStatus")
        return int(status.value)

    def data_after_exposure(self, camera_id: int, size: int) -> bytes:
        buffer = (ctypes.c_ubyte * size)()
        self.check(self.lib.ASIGetDataAfterExp(camera_id, buffer, size), "ASIGetDataAfterExp")
        return bytes(buffer)


class ZwoAsiAdapter(CameraAdapter):
    id = "zwo"
    name = "ZWO ASI"
    backend = "zwo"
    supports_hard_cancel = True

    def __init__(self, sdk: Any | None = None, cli_tool: str | None = None, print_tool: str | None = None, dump_tool: str | None = None) -> None:
        self._sdk = sdk
        self._active_camera_by_job: dict[str, int] = {}
        self._active_cli_by_job: dict[str, subprocess.Popen] = {}
        self._canceled_jobs: set[str] = set()
        self._cli_tool = cli_tool or shutil.which("zwo-asi-shot")
        self._print_tool = print_tool or shutil.which("zwo-asi-print")
        self._dump_tool = dump_tool or shutil.which("zwo-asi-dump")

    def _get_sdk(self) -> Any:
        """Return a loaded ``ZwoSdk`` instance.

        If the SDK cannot be loaded we raise ``ZwoSdkError`` which signals the
        caller to use the CLI fallback.
        """
        if self._sdk is None:
            # Attempt to load the native SDK; any error propagates as
            # ``ZwoSdkError``.
            self._sdk = ZwoSdk()
        return self._sdk

    async def detect(self) -> list[DetectedCamera]:
        try:
            return await asyncio.to_thread(self._detect_sync)
        except ZwoSdkUnavailable:
            if not self._print_tool:
                return []
            return await self._detect_cli()

    def _detect_sync(self) -> list[DetectedCamera]:
        sdk = self._get_sdk()
        cameras: list[DetectedCamera] = []
        for index in range(sdk.camera_count()):
            info = sdk.camera_property(index)
            cameras.append(self._detected_from_info(info))
        return cameras

    async def _detect_cli(self) -> list[DetectedCamera]:
        proc = await asyncio.create_subprocess_exec(
            self._print_tool,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return []
        return parse_zwo_print_output(stdout.decode(errors="replace"))

    def _detected_from_info(self, info: ASICameraInfo) -> DetectedCamera:
        name = decode_c_string(bytes(info.Name)) or f"ZWO ASI {info.CameraID}"
        formats = supported_ints(info.SupportedVideoFormat)
        return DetectedCamera(
            id=f"zwo://{int(info.CameraID)}",
            name=name,
            backend=self.backend,
            model=name,
            serial=str(int(info.CameraID)),
            metadata={
                "camera_id": int(info.CameraID),
                "max_width": int(info.MaxWidth),
                "max_height": int(info.MaxHeight),
                "is_color": bool(info.IsColorCam),
                "is_cooler": bool(info.IsCoolerCam),
                "pixel_size_um": float(info.PixelSize),
                "bit_depth": int(info.BitDepth),
                "supported_bins": [value for value in supported_ints(info.SupportedBins) if value],
                "supported_image_types": formats,
            },
        )

    async def connect(self, camera_id: str) -> CameraInfo:
        try:
            info = await asyncio.to_thread(self._camera_info_for_device, camera_id)
            name = decode_c_string(bytes(info.Name)) or f"ZWO ASI {info.CameraID}"
            return CameraInfo(id=f"zwo://{int(info.CameraID)}", name=name, backend=self.backend, model=name, serial=str(int(info.CameraID)))
        except ZwoSdkUnavailable:
            parsed = self._parse_camera_id(camera_id)
            name = f"ZWO ASI {parsed}" if parsed is not None else "ZWO ASI"
            return CameraInfo(id=camera_id or "zwo://default", name=name, backend=self.backend, model=name, serial=str(parsed) if parsed is not None else None)

    async def get_capabilities(self) -> CameraCapabilities:
        return await self.get_capabilities_for_device(None)

    async def get_capabilities_for_device(self, device_id: str | None) -> CameraCapabilities:
        try:
            info = await asyncio.to_thread(self._camera_info_for_device, device_id)
        except ZwoSdkUnavailable:
            return CameraCapabilities(
                formats=["jpg", "png"],
                controls=["exposure_ms", "gain", "width", "height", "cooling", "target_temperature_c", "zwo_cli_config", "zwo_cli_args"],
                max_exposure_ms=120000,
                cooling=False,
                raw={
                    "sdk_available": False,
                    "cli_available": bool(self._cli_tool),
                    "install_hint": "Install camera-zwo-asi for zwo-asi-shot support, or install the ZWO ASI Camera SDK and set SKYWEAVER_ZWO_SDK_LIBRARY.",
                },
            )
        return CameraCapabilities(
            formats=["jpg", "png"],
            controls=["exposure_ms", "gain", "width", "height", "cooling", "target_temperature_c"],
            max_exposure_ms=120000,
            cooling=bool(info.IsCoolerCam),
            raw=self._detected_from_info(info).metadata,
        )

    async def get_settings_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "exposure_ms": {"type": "number", "minimum": 0.001, "maximum": 120000},
                "gain": {"type": "number", "minimum": 0},
                "width": {"type": "integer", "minimum": 8},
                "height": {"type": "integer", "minimum": 2},
                "format": {"type": "string", "enum": ["jpg", "png"]},
                "cooling": {"type": "boolean"},
                "target_temperature_c": {"type": "number"},
            },
        }

    async def capture(self, request: CaptureRequest) -> CaptureResult:
        return await asyncio.to_thread(self._capture_sync, request)

    def _camera_info_for_device(self, device_id: str | None) -> ASICameraInfo:
        sdk = self._get_sdk()
        camera_id = self._parse_camera_id(device_id)
        if camera_id is not None:
            for index in range(sdk.camera_count()):
                info = sdk.camera_property(index)
                if int(info.CameraID) == camera_id:
                    return info
            raise ZwoSdkError(f"ZWO camera id {camera_id} was not found.")
        if sdk.camera_count() < 1:
            raise ZwoSdkError("No ZWO ASI cameras detected.")
        return sdk.camera_property(0)

    @staticmethod
    def _parse_camera_id(device_id: str | None) -> int | None:
        if not device_id:
            return None
        if device_id == "zwo://default":
            return None
        try:
            if device_id.startswith("zwo://"):
                return int(device_id.removeprefix("zwo://"))
            return int(device_id)
        except ValueError as exc:
            raise ZwoSdkError(f"Invalid ZWO camera device_id: {device_id}") from exc

    @staticmethod
    def _choose_image_type(info: ASICameraInfo) -> int:
        supported = set(supported_ints(info.SupportedVideoFormat))
        if bool(info.IsColorCam) and ASI_IMG_RGB24 in supported:
            return ASI_IMG_RGB24
        if ASI_IMG_Y8 in supported:
            return ASI_IMG_Y8
        if ASI_IMG_RAW8 in supported:
            return ASI_IMG_RAW8
        raise ZwoSdkError("ZWO camera does not advertise an 8-bit RGB or mono format that Sky Weaver can save yet.")

    @staticmethod
    def _buffer_size(width: int, height: int, image_type: int) -> int:
        if image_type == ASI_IMG_RGB24:
            return width * height * 3
        if image_type == ASI_IMG_RAW16:
            return width * height * 2
        return width * height

    @staticmethod
    def _save_image(data: bytes, path: Path, width: int, height: int, image_type: int, image_format: str) -> None:
        if image_type == ASI_IMG_RGB24:
            image = Image.frombytes("RGB", (width, height), data)
        else:
            image = Image.frombytes("L", (width, height), data)
        fmt = "JPEG" if image_format.lower() in {"jpg", "jpeg"} else "PNG"
        image.save(path, fmt, quality=92)

    def _capture_sync(self, request: CaptureRequest) -> CaptureResult:
        """Capture using the native SDK, falling back to the CLI tool.

        The SDK path is attempted first because it provides fine‑grained
        control. If loading the SDK raises ``ZwoSdkUnavailable`` we invoke
        ``zwo-asi-shot`` through the ``camera-zwo-asi`` package. Other SDK
        errors fail fast so hardware problems are not hidden by a second capture
        attempt.
        """
        # Try native SDK first.
        try:
            sdk = self._get_sdk()
            info = self._camera_info_for_device(request.settings.get("device_id"))
            camera_id = int(info.CameraID)
            width = min(int(request.width or info.MaxWidth), int(info.MaxWidth))
            height = min(int(request.height or info.MaxHeight), int(info.MaxHeight))
            width -= width % 8
            height -= height % 2
            if width <= 0 or height <= 0:
                raise ZwoSdkError("ZWO capture width/height resolved to an invalid ROI.")
            image_type = self._choose_image_type(info)
            path = request.output_path
            path.parent.mkdir(parents=True, exist_ok=True)
            job_key = request.job_id or str(path)
            if job_key in self._canceled_jobs:
                raise CaptureCanceled("Capture canceled by operator stop")

            sdk.open(camera_id)
            try:
                sdk.init(camera_id)
                sdk.set_control(camera_id, ASI_EXPOSURE, int(request.exposure_ms * 1000))
                sdk.set_control(camera_id, ASI_GAIN, int(request.gain))
                if "cooling" in request.settings:
                    sdk.set_control(camera_id, ASI_COOLER_ON, 1 if request.settings["cooling"] else 0)
                if request.settings.get("target_temperature_c") is not None:
                    sdk.set_control(camera_id, ASI_TARGET_TEMP, int(request.settings["target_temperature_c"]))
                sdk.set_roi(camera_id, width, height, image_type)
                self._active_camera_by_job[job_key] = camera_id
                sdk.start_exposure(camera_id, bool(request.settings.get("dark_frame", False)))
                deadline = time.monotonic() + max(5.0, (request.exposure_ms / 1000.0) + 30.0)
                while True:
                    if job_key in self._canceled_jobs:
                        sdk.stop_exposure(camera_id)
                        raise CaptureCanceled("Capture canceled by operator stop")
                    status = sdk.exposure_status(camera_id)
                    if status == ASI_EXP_SUCCESS:
                        break
                    if status == ASI_EXP_FAILED:
                        raise ZwoSdkError("ZWO exposure failed.")
                    if status not in {ASI_EXP_IDLE, ASI_EXP_WORKING}:
                        raise ZwoSdkError(f"Unexpected ZWO exposure status: {status}")
                    if time.monotonic() > deadline:
                        sdk.stop_exposure(camera_id)
                        raise ZwoSdkError("ZWO exposure timed out.")
                    time.sleep(0.1)
                data = sdk.data_after_exposure(camera_id, self._buffer_size(width, height, image_type))
                if job_key in self._canceled_jobs:
                    raise CaptureCanceled("Capture canceled by operator stop")
                self._save_image(data, path, width, height, image_type, request.image_format)
                temperature = sdk.get_control(camera_id, ASI_TEMPERATURE)
                return CaptureResult(
                    file_path=path,
                    format=request.image_format.lower(),
                    width=width,
                    height=height,
                    size_bytes=path.stat().st_size,
                    exposure_ms=request.exposure_ms,
                    gain=request.gain,
                    temperature_c=(temperature / 10.0) if temperature is not None else None,
                    metadata={"adapter": self.backend, "camera_id": camera_id, "image_type": image_type, "sdk_library": getattr(sdk, "library_path", None)},
                )
            finally:
                self._active_camera_by_job.pop(job_key, None)
                self._canceled_jobs.discard(job_key)
                sdk.close(camera_id)
        except ZwoSdkUnavailable:
            if not self._cli_tool:
                raise
            return self._capture_cli(request)

    def _capture_cli(self, request: CaptureRequest) -> CaptureResult:
        path = request.output_path
        path.parent.mkdir(parents=True, exist_ok=True)
        job_key = request.job_id or str(path)
        if job_key in self._canceled_jobs:
            raise CaptureCanceled("Capture canceled by operator stop")

        config_dir = self._cli_config_dir(request)
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / ZWO_CLI_CONFIG
        dump_first = bool(request.settings.get("zwo_cli_dump", not config_path.exists()))
        if dump_first and self._dump_tool:
            self._run_cli([self._dump_tool], config_dir, job_key, timeout=30)

        updates = self._cli_config_updates(request, path)
        existing = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
        config_path.write_text(merge_toml_lines(existing, updates), encoding="utf-8")

        extra_args = [str(value) for value in request.settings.get("zwo_cli_args", [])]
        shot_args = [self._cli_tool, "-silent", "--path", str(path), *extra_args]
        camera_id = self._parse_camera_id(request.settings.get("device_id"))
        if camera_id is not None:
            shot_args.extend(["--index", str(camera_id)])
        self._run_cli(shot_args, config_dir, job_key, timeout=max(30.0, (request.exposure_ms / 1000.0) + 60.0))
        if not path.exists():
            generated = self._latest_generated_cli_image(config_dir, config_path)
            if generated:
                generated.replace(path)
        if not path.exists():
            raise RuntimeError(f"zwo-asi-shot completed but did not write {path}")
        return CaptureResult(
            file_path=path,
            format=request.image_format.lower(),
            width=request.width or self._image_dimension(path, 0),
            height=request.height or self._image_dimension(path, 1),
            size_bytes=path.stat().st_size,
            exposure_ms=request.exposure_ms,
            gain=request.gain,
            metadata={"adapter": self.backend, "backend_mode": "camera-zwo-asi", "config_path": str(config_path)},
        )

    def _run_cli(self, args: list[str], cwd: Path, job_key: str, timeout: float) -> None:
        proc = subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self._active_cli_by_job[job_key] = proc
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
            raise RuntimeError(f"{Path(args[0]).name} timed out: {(stderr or stdout).strip()}") from exc
        finally:
            self._active_cli_by_job.pop(job_key, None)
        if job_key in self._canceled_jobs:
            raise CaptureCanceled("Capture canceled by operator stop")
        if proc.returncode != 0:
            raise RuntimeError(f"{Path(args[0]).name} failed: {(stderr or stdout).strip()}")

    def _cli_config_dir(self, request: CaptureRequest) -> Path:
        configured = request.settings.get("zwo_cli_config_dir") or os.environ.get("SKYWEAVER_ZWO_CONFIG_DIR")
        if configured:
            return Path(str(configured))
        return request.output_path.parent / ".zwo"

    def _cli_config_updates(self, request: CaptureRequest, output_path: Path) -> dict[str, Any]:
        updates: dict[str, Any] = {
            "controllables.Exposure": int(request.exposure_ms * 1000),
            "controllables.Gain": int(request.gain),
        }
        if request.width:
            updates["roi.width"] = int(request.width)
        if request.height:
            updates["roi.height"] = int(request.height)
        if request.settings.get("cooling") is not None:
            updates["controllables.CoolerOn"] = bool(request.settings["cooling"])
        if request.settings.get("target_temperature_c") is not None:
            updates["controllables.TargetTemp"] = float(request.settings["target_temperature_c"])
        extra = request.settings.get("zwo_cli_config")
        if isinstance(extra, dict):
            updates.update(extra)
        return updates

    @staticmethod
    def _latest_generated_cli_image(config_dir: Path, config_path: Path) -> Path | None:
        candidates = [
            path
            for path in config_dir.iterdir()
            if path.is_file() and path != config_path and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".fits", ".tif", ".tiff"}
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: candidate.stat().st_mtime)

    @staticmethod
    def _image_dimension(path: Path, index: int) -> int | None:
        try:
            with Image.open(path) as img:
                return img.size[index]
        except Exception:
            return None

    async def cancel_capture(self, job_id: str, reason: str = "operator stop") -> CaptureCancelResult:
        camera_id = self._active_camera_by_job.get(job_id)
        cli_proc = self._active_cli_by_job.get(job_id)
        if cli_proc is not None:
            self._canceled_jobs.add(job_id)
            await asyncio.to_thread(cli_proc.terminate)
            return CaptureCancelResult(supported=True, canceled=True, method="terminate", message=reason)
        if camera_id is None:
            self._canceled_jobs.add(job_id)
            return CaptureCancelResult(supported=True, canceled=False, method="sdk", message="No active ZWO exposure for this job yet")
        self._canceled_jobs.add(job_id)
        await asyncio.to_thread(self._get_sdk().stop_exposure, camera_id)
        return CaptureCancelResult(supported=True, canceled=True, method="ASIStopExposure", message=reason)
