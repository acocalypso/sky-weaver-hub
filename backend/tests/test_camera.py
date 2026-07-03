import os
from pathlib import Path

import pytest

from skyweaver.camera.base import CaptureRequest
from skyweaver.camera.mock import MockCameraAdapter
from skyweaver.camera.registry import get_adapter
from skyweaver.camera.rpicam import RpiCamAdapter
import skyweaver.camera.rpicam as rpicam_module
from skyweaver.camera.zwo import ASI_EXP_SUCCESS, ASI_EXP_WORKING, ASI_EXPOSURE, ASI_GAIN, ASI_IMG_END, ASI_IMG_RGB24, ASI_TEMPERATURE, ASICameraInfo, ZwoAsiAdapter, ZwoSdk


def zwo_camera_info(camera_id: int = 2) -> ASICameraInfo:
    info = ASICameraInfo()
    info.Name = b"ASI294MC Pro"
    info.CameraID = camera_id
    info.MaxWidth = 16
    info.MaxHeight = 8
    info.IsColorCam = 1
    info.IsCoolerCam = 1
    info.PixelSize = 4.63
    info.BitDepth = 14
    info.SupportedBins[0] = 1
    info.SupportedVideoFormat[0] = ASI_IMG_RGB24
    info.SupportedVideoFormat[1] = ASI_IMG_END
    return info


class FakeZwoSdk:
    library_path = "/opt/zwo/libASICamera2.so"

    def __init__(self) -> None:
        self.info = zwo_camera_info()
        self.calls: list[tuple] = []
        self.statuses = [ASI_EXP_WORKING, ASI_EXP_SUCCESS]

    def camera_count(self) -> int:
        return 1

    def camera_property(self, index: int) -> ASICameraInfo:
        assert index == 0
        return self.info

    def open(self, camera_id: int) -> None:
        self.calls.append(("open", camera_id))

    def init(self, camera_id: int) -> None:
        self.calls.append(("init", camera_id))

    def close(self, camera_id: int) -> None:
        self.calls.append(("close", camera_id))

    def set_control(self, camera_id: int, control_type: int, value: int) -> None:
        self.calls.append(("set_control", camera_id, control_type, value))

    def get_control(self, camera_id: int, control_type: int) -> int | None:
        assert control_type == ASI_TEMPERATURE
        self.calls.append(("get_control", camera_id, control_type))
        return 125

    def set_roi(self, camera_id: int, width: int, height: int, image_type: int) -> None:
        self.calls.append(("set_roi", camera_id, width, height, image_type))

    def start_exposure(self, camera_id: int, dark: bool = False) -> None:
        self.calls.append(("start_exposure", camera_id, dark))

    def stop_exposure(self, camera_id: int) -> None:
        self.calls.append(("stop_exposure", camera_id))

    def exposure_status(self, camera_id: int) -> int:
        self.calls.append(("exposure_status", camera_id))
        return self.statuses.pop(0)

    def data_after_exposure(self, camera_id: int, size: int) -> bytes:
        self.calls.append(("data_after_exposure", camera_id, size))
        return bytes([32, 64, 128]) * (size // 3)


@pytest.mark.asyncio
async def test_mock_camera_capture(tmp_path: Path):
    adapter = MockCameraAdapter()
    found = await adapter.detect()
    assert found[0].backend == "mock"
    result = await adapter.capture(CaptureRequest(output_path=tmp_path / "mock.jpg", exposure_ms=1000, gain=1))
    assert result.file_path.exists()
    assert result.width == 1280
    assert result.size_bytes and result.size_bytes > 0


@pytest.mark.asyncio
async def test_rpicam_detect_parses_only_numbered_camera_rows(tmp_path: Path, monkeypatch):
    if os.name == "nt":
        tool = tmp_path / "rpicam-hello.bat"
        tool.write_text(
            """@echo off
echo Available cameras
echo -----------------
echo 0 : imx290 [1920x1080 12-bit RGGB] (/base/soc/i2c0mux/i2c@1/imx290@1a)
echo     Modes: 'SRGGB10_CSI2P' : 1280x720 [60.00 fps - (320, 180)/1280x720 crop]
echo                              1920x1080 [60.00 fps - (0, 0)/1920x1080 crop]
echo            'SRGGB12_CSI2P' : 1280x720 [60.00 fps - (320, 180)/1280x720 crop]
echo                              1920x1080 [60.00 fps - (0, 0)/1920x1080 crop]
""",
            encoding="utf-8",
        )
    else:
        tool = tmp_path / "rpicam-hello"
        tool.write_text(
            """#!/usr/bin/env bash
cat <<'OUT'
Available cameras
-----------------
0 : imx290 [1920x1080 12-bit RGGB] (/base/soc/i2c0mux/i2c@1/imx290@1a)
    Modes: 'SRGGB10_CSI2P' : 1280x720 [60.00 fps - (320, 180)/1280x720 crop]
                             1920x1080 [60.00 fps - (0, 0)/1920x1080 crop]
           'SRGGB12_CSI2P' : 1280x720 [60.00 fps - (320, 180)/1280x720 crop]
                             1920x1080 [60.00 fps - (0, 0)/1920x1080 crop]
OUT
""",
            encoding="utf-8",
        )
    tool.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))

    found = await RpiCamAdapter().detect()

    assert len(found) == 1
    assert found[0].id == "rpicam://0"
    model = found[0].model
    assert model is not None
    assert "imx290" in model
    assert found[0].name == "imx290 camera 0"
    assert found[0].metadata["sensor"] == "imx290"
    assert found[0].metadata["path"] == "/base/soc/i2c0mux/i2c@1/imx290@1a"
    assert found[0].metadata["width"] == 1920
    assert found[0].metadata["height"] == 1080
    assert found[0].metadata["bit_depth"] == 12
    assert found[0].metadata["bayer_order"] == "RGGB"
    assert found[0].metadata["modes"][0] == {
        "pixel_format": "SRGGB10_CSI2P",
        "width": 1280,
        "height": 720,
        "fps": 60.0,
        "crop": {"x": 320, "y": 180, "width": 1280, "height": 720},
    }
    assert found[0].metadata["modes"][-1]["pixel_format"] == "SRGGB12_CSI2P"


def test_rpicam_parse_camera_list_supports_multiple_cameras():
    text = """Available cameras
-----------------
0 : imx290 [1920x1080 12-bit RGGB] (/base/soc/i2c0mux/i2c@1/imx290@1a)
    Modes: 'SRGGB10_CSI2P' : 1280x720 [60.00 fps - (320, 180)/1280x720 crop]
                             1920x1080 [60.00 fps - (0, 0)/1920x1080 crop]
1 : imx708 [4608x2592 10-bit RGGB] (/base/soc/i2c0mux/i2c@1/imx708@1a)
    Modes: 'SRGGB10_CSI2P' : 2304x1296 [56.03 fps - (0, 0)/4608x2592 crop]
"""

    found = RpiCamAdapter()._parse_camera_list(text)

    assert [camera.id for camera in found] == ["rpicam://0", "rpicam://1"]
    assert found[1].name == "imx708 camera 1"
    assert found[1].metadata["sensor"] == "imx708"
    assert found[1].metadata["width"] == 2304
    assert found[1].metadata["height"] == 1296
    assert found[1].metadata["bit_depth"] == 10
    assert found[1].metadata["modes"][0]["crop"] == {"x": 0, "y": 0, "width": 4608, "height": 2592}


def test_camera_registry_reuses_adapter_instances():
    first = get_adapter("rpicam")
    second = get_adapter("rpicam")

    assert first is second


@pytest.mark.asyncio
async def test_rpicam_cancel_capture_terminates_active_process(tmp_path: Path):
    adapter = RpiCamAdapter()
    output = tmp_path / "partial.jpg"
    output.write_bytes(b"partial")

    class FakeProcess:
        returncode = None

        def __init__(self) -> None:
            self.terminated = False
            self.killed = False

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

        async def wait(self) -> int:
            self.returncode = -15
            return self.returncode

    proc = FakeProcess()
    adapter._active_processes["job-1"] = (proc, output)

    result = await adapter.cancel_capture("job-1", "Operator stop")

    assert result.supported is True
    assert result.canceled is True
    assert result.method == "terminate"
    assert proc.terminated is True
    assert proc.killed is False
    assert not output.exists()


@pytest.mark.asyncio
async def test_rpicam_one_shot_capture_uses_headless_preview_flag(tmp_path: Path, monkeypatch):
    output = tmp_path / "single.jpg"
    calls: list[list[str]] = []

    class FakeProcess:
        returncode = 0
        stdout = None
        stderr = None

        async def communicate(self):
            output.write_bytes(b"jpg")
            return b"", b""

    async def fake_exec(*args, **_kwargs):
        calls.append(list(args))
        return FakeProcess()

    monkeypatch.setattr("skyweaver.camera.rpicam.shutil.which", lambda name: "/usr/bin/rpicam-still" if name == "rpicam-still" else None)
    monkeypatch.setattr("skyweaver.camera.rpicam.asyncio.create_subprocess_exec", fake_exec)

    result = await RpiCamAdapter().capture(
        CaptureRequest(
            output_path=output,
            exposure_ms=1000,
            gain=1,
            width=1280,
            height=960,
            image_format="jpg",
            settings={
                "persistent": False,
                "quality": 88,
                "denoise": "cdn_fast",
                "auto_white_balance": False,
                "red_balance": 1.4,
                "blue_balance": 1.8,
                "hflip": True,
                "vflip": True,
                "rotation": 180,
                "roi": [0.1, 0.2, 0.7, 0.6],
                "brightness": 0.2,
                "contrast": 1.5,
                "saturation": 0.8,
                "sharpness": 1.2,
                "sensor_mode": "1920:1080:12:P",
                "tuning_file": "/opt/camera/imx290.json",
            },
        )
    )

    assert result.file_path == output
    assert output.exists()
    assert "--immediate" in calls[0]
    assert "--nopreview" in calls[0]
    assert "--signal" not in calls[0]
    assert calls[0][calls[0].index("--encoding") + 1] == "jpg"
    assert calls[0][calls[0].index("--quality") + 1] == "88"
    assert calls[0][calls[0].index("--denoise") + 1] == "cdn_fast"
    assert calls[0][calls[0].index("--awbgains") + 1] == "1.4,1.8"
    assert "--hflip" in calls[0]
    assert "--vflip" in calls[0]
    assert calls[0][calls[0].index("--rotation") + 1] == "180"
    assert calls[0][calls[0].index("--roi") + 1] == "0.1,0.2,0.7,0.6"
    assert calls[0][calls[0].index("--brightness") + 1] == "0.2"
    assert calls[0][calls[0].index("--contrast") + 1] == "1.5"
    assert calls[0][calls[0].index("--saturation") + 1] == "0.8"
    assert calls[0][calls[0].index("--sharpness") + 1] == "1.2"
    assert calls[0][calls[0].index("--mode") + 1] == "1920:1080:12:P"
    assert calls[0][calls[0].index("--tuning-file") + 1] == "/opt/camera/imx290.json"


@pytest.mark.asyncio
async def test_rpicam_persistent_signal_session_reuses_process(tmp_path: Path, monkeypatch):
    calls: list[list[str]] = []
    processes: list["FakeSignalProcess"] = []

    class FakeSignalProcess:
        returncode = None
        stdout = None
        stderr = None

        def __init__(self, args: tuple[str, ...]) -> None:
            self.args = args
            self.terminated = False
            self.waited = False
            output_index = args.index("--output") + 1
            self.pattern = Path(args[output_index])
            self.index = 0

        def send_signal(self, signum: int) -> None:
            assert signum == rpicam_module.SIGUSR1
            path = Path(str(self.pattern).replace("%04d", f"{self.index:04d}"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"frame-{self.index}".encode("ascii"))
            self.index += 1

        def terminate(self) -> None:
            self.terminated = True
            self.returncode = -15

        def kill(self) -> None:
            self.returncode = -9

        async def wait(self) -> int:
            self.waited = True
            if self.returncode is None:
                self.returncode = 0
            return self.returncode

    async def fake_exec(*args, **_kwargs):
        calls.append(list(args))
        proc = FakeSignalProcess(tuple(args))
        processes.append(proc)
        return proc

    monkeypatch.setattr("skyweaver.camera.rpicam.shutil.which", lambda name: "/usr/bin/rpicam-still" if name == "rpicam-still" else None)
    monkeypatch.setattr("skyweaver.camera.rpicam.asyncio.create_subprocess_exec", fake_exec)
    monkeypatch.setattr("skyweaver.camera.rpicam.SIGUSR1", 10)

    adapter = RpiCamAdapter()
    request = {
        "exposure_ms": 1000,
        "gain": 4,
        "width": 1280,
        "height": 960,
        "image_format": "jpg",
        "settings": {"persistent_warmup_seconds": 0, "awb": "cloudy", "quality": 90},
    }

    first = await adapter.capture(CaptureRequest(output_path=tmp_path / "first.jpg", job_id="job-1", **request))
    second = await adapter.capture(CaptureRequest(output_path=tmp_path / "second.jpg", job_id="job-2", **request))
    await adapter.disconnect()

    assert first.file_path.read_bytes() == b"frame-0"
    assert second.file_path.read_bytes() == b"frame-1"
    assert first.metadata["capture_mode"] == "persistent_signal"
    assert second.metadata["capture_mode"] == "persistent_signal"
    assert len(calls) == 1
    assert "--signal" in calls[0]
    assert "--nopreview" in calls[0]
    assert "--immediate" not in calls[0]
    assert calls[0][calls[0].index("--awb") + 1] == "cloudy"
    assert calls[0][calls[0].index("--quality") + 1] == "90"
    assert processes[0].terminated is True


@pytest.mark.asyncio
async def test_rpicam_persistent_failure_falls_back_to_one_shot(tmp_path: Path, monkeypatch):
    output = tmp_path / "fallback.jpg"
    calls: list[list[str]] = []

    class FailingPersistentProcess:
        stdout = None
        stderr = None
        returncode = None

        def send_signal(self, _signum: int) -> None:
            self.returncode = 1

        def terminate(self) -> None:
            self.returncode = -15

        def kill(self) -> None:
            self.returncode = -9

        async def wait(self) -> int:
            return self.returncode or 0

    class OneShotProcess:
        stdout = None
        stderr = None
        returncode = 0

        async def communicate(self):
            output.write_bytes(b"one-shot")
            return b"", b""

    async def fake_exec(*args, **_kwargs):
        calls.append(list(args))
        if "--signal" in args:
            return FailingPersistentProcess()
        return OneShotProcess()

    monkeypatch.setattr("skyweaver.camera.rpicam.shutil.which", lambda name: "/usr/bin/rpicam-still" if name == "rpicam-still" else None)
    monkeypatch.setattr("skyweaver.camera.rpicam.asyncio.create_subprocess_exec", fake_exec)
    monkeypatch.setattr("skyweaver.camera.rpicam.SIGUSR1", 10)

    result = await RpiCamAdapter().capture(
        CaptureRequest(
            output_path=output,
            job_id="job-fallback",
            exposure_ms=1000,
            gain=1,
            width=1280,
            height=960,
            image_format="jpg",
            settings={"persistent_warmup_seconds": 0},
        )
    )

    assert output.read_bytes() == b"one-shot"
    assert result.metadata["capture_mode"] == "one_shot_after_persistent_failure"
    assert "persistent capture process exited before writing an image" in result.metadata["persistent_error"]
    assert "--signal" in calls[0]
    assert "--immediate" in calls[1]


@pytest.mark.asyncio
async def test_zwo_detect_reports_sdk_camera():
    adapter = ZwoAsiAdapter(sdk=FakeZwoSdk())

    found = await adapter.detect()

    assert len(found) == 1
    assert found[0].id == "zwo://2"
    assert found[0].backend == "zwo"
    assert found[0].model == "ASI294MC Pro"
    assert found[0].metadata["max_width"] == 16
    assert found[0].metadata["is_cooler"] is True
    assert found[0].metadata["supported_image_types"] == [ASI_IMG_RGB24]


@pytest.mark.asyncio
async def test_zwo_capture_uses_sdk_and_writes_image(tmp_path: Path):
    sdk = FakeZwoSdk()
    adapter = ZwoAsiAdapter(sdk=sdk)
    output = tmp_path / "zwo.jpg"

    result = await adapter.capture(
        CaptureRequest(
            output_path=output,
            job_id="job-zwo",
            exposure_ms=250,
            gain=42,
            width=16,
            height=8,
            image_format="jpg",
            settings={"device_id": "zwo://2", "cooling": True, "target_temperature_c": -10},
        )
    )

    assert output.exists()
    assert result.width == 16
    assert result.height == 8
    assert result.size_bytes and result.size_bytes > 0
    assert result.temperature_c == 12.5
    assert result.metadata["adapter"] == "zwo"
    assert ("set_control", 2, ASI_EXPOSURE, 250000) in sdk.calls
    assert ("set_control", 2, ASI_GAIN, 42) in sdk.calls
    assert ("set_roi", 2, 16, 8, ASI_IMG_RGB24) in sdk.calls
    assert ("data_after_exposure", 2, 16 * 8 * 3) in sdk.calls
    assert sdk.calls[-1] == ("close", 2)


def test_zwo_sdk_find_library_checks_debian_multiarch_path(monkeypatch):
    debian_path = "/usr/lib/aarch64-linux-gnu/libASICamera2.so"
    monkeypatch.delenv("SKYWEAVER_ZWO_SDK_LIBRARY", raising=False)
    monkeypatch.setattr("skyweaver.camera.zwo.ctypes.util.find_library", lambda _name: None)
    monkeypatch.setattr("skyweaver.camera.zwo.glob.glob", lambda pattern: [debian_path] if pattern == "/usr/lib/*-linux-gnu/libASICamera2.so" else [])
    monkeypatch.setattr("skyweaver.camera.zwo.Path.exists", lambda self: self.as_posix().endswith("usr/lib/aarch64-linux-gnu/libASICamera2.so"))
    monkeypatch.setattr("skyweaver.camera.zwo.Path.resolve", lambda self: self)

    assert ZwoSdk.find_library().replace("\\", "/") == debian_path
