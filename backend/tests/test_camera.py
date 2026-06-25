from pathlib import Path
import os

import pytest

from skyweaver.camera.base import CaptureRequest
from skyweaver.camera.mock import MockCameraAdapter
from skyweaver.camera.rpicam import RpiCamAdapter
from skyweaver.camera.zwo import ASI_EXP_SUCCESS, ASI_EXP_WORKING, ASI_EXPOSURE, ASI_GAIN, ASI_IMG_END, ASI_IMG_RGB24, ASI_TEMPERATURE, ASICameraInfo, ZwoAsiAdapter


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
