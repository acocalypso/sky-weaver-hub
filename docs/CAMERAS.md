# Cameras

Adapters:

- `mock`: generates synthetic all-sky images for development and CI.
- `rpicam` / `libcamera`: Raspberry Pi camera path via `rpicam-still` or `libcamera-still`; IMX290 test shots and hard-cancel through `/api/v1/capture/stop` have passed on a Raspberry Pi.
- `zwo`: initial SDK-backed ZWO ASI adapter. It detects cameras and captures still images through `libASICamera2` when the ZWO ASI Camera SDK is installed. Set `SKYWEAVER_ZWO_SDK_LIBRARY` if the shared library is not discoverable through the system loader.
- `gphoto2`, `v4l2`, `indi`, `custom_command`: extension points with API-visible errors until fully implemented.

The browser never calls camera commands directly. All camera actions go through `/api/v1` and the backend adapter interface.

ZWO support is intentionally not a mock. Without the ASI SDK library, detection returns no ZWO cameras and capabilities include an install hint. Real ZWO hardware validation is still pending.
