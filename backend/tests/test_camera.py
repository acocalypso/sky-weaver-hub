from pathlib import Path

import pytest

from skyweaver.camera.base import CaptureRequest
from skyweaver.camera.mock import MockCameraAdapter


@pytest.mark.asyncio
async def test_mock_camera_capture(tmp_path: Path):
    adapter = MockCameraAdapter()
    found = await adapter.detect()
    assert found[0].backend == "mock"
    result = await adapter.capture(CaptureRequest(output_path=tmp_path / "mock.jpg", exposure_ms=1000, gain=1))
    assert result.file_path.exists()
    assert result.width == 1280
    assert result.size_bytes and result.size_bytes > 0
