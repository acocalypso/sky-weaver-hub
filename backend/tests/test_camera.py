from pathlib import Path
import os

import pytest

from skyweaver.camera.base import CaptureRequest
from skyweaver.camera.mock import MockCameraAdapter
from skyweaver.camera.rpicam import RpiCamAdapter


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
    monkeypatch.setenv("PATH", str(tmp_path))

    found = await RpiCamAdapter().detect()

    assert len(found) == 1
    assert found[0].id == "rpicam://0"
    assert "imx290" in found[0].model
