from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DetectedCamera:
    id: str
    name: str
    backend: str
    model: str | None = None
    serial: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CameraInfo:
    id: str
    name: str
    backend: str
    model: str | None = None
    serial: str | None = None


@dataclass
class CameraCapabilities:
    formats: list[str]
    controls: list[str]
    max_exposure_ms: int | None = None
    cooling: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaptureRequest:
    output_path: Path
    job_id: str | None = None
    exposure_ms: float = 1000
    gain: float = 1.0
    width: int | None = None
    height: int | None = None
    image_format: str = "jpg"
    mode: str = "manual"
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaptureResult:
    file_path: Path
    format: str
    width: int | None = None
    height: int | None = None
    size_bytes: int | None = None
    exposure_ms: float | None = None
    gain: float | None = None
    temperature_c: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaptureCancelResult:
    supported: bool
    canceled: bool = False
    method: str | None = None
    message: str | None = None


class CaptureCanceled(RuntimeError):
    pass


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PreviewResult:
    url: str | None = None
    message: str | None = None


class CameraAdapter(ABC):
    id: str
    name: str
    backend: str
    supports_hard_cancel: bool = False

    @abstractmethod
    async def detect(self) -> list[DetectedCamera]:
        raise NotImplementedError

    @abstractmethod
    async def connect(self, camera_id: str) -> CameraInfo:
        raise NotImplementedError

    async def disconnect(self) -> None:
        return None

    @abstractmethod
    async def get_capabilities(self) -> CameraCapabilities:
        raise NotImplementedError

    async def get_settings_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "exposure_ms": {"type": "number", "minimum": 0.001},
                "gain": {"type": "number", "minimum": 0},
                "width": {"type": "integer", "minimum": 1},
                "height": {"type": "integer", "minimum": 1},
                "format": {"type": "string", "enum": ["jpg", "png"]},
            },
        }

    async def validate_settings(self, settings: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        if float(settings.get("exposure_ms", 1)) <= 0:
            errors.append("exposure_ms must be positive")
        if float(settings.get("gain", 0)) < 0:
            errors.append("gain must be zero or greater")
        return ValidationResult(ok=not errors, errors=errors)

    @abstractmethod
    async def capture(self, request: CaptureRequest) -> CaptureResult:
        raise NotImplementedError

    async def cancel_capture(self, job_id: str, reason: str = "operator stop") -> CaptureCancelResult:
        return CaptureCancelResult(supported=False, message="Hard capture cancellation is not supported by this adapter")

    async def start_preview(self) -> PreviewResult:
        return PreviewResult(message="Preview is not implemented for this adapter")

    async def stop_preview(self) -> None:
        return None

    async def get_temperature(self) -> float | None:
        return None

    async def set_cooling(self, enabled: bool, target_c: float | None) -> None:
        raise NotImplementedError("Cooling is not supported by this adapter")
