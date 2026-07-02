# Cameras

Adapters:

- `mock`: generates synthetic all-sky images for development and CI.
- `rpicam` / `libcamera`: Raspberry Pi camera path via `rpicam-still` or `libcamera-still`; detection parses sensor, device path, resolution, bit depth, Bayer order, and capture modes from `rpicam-hello --list-cameras`. IMX290 test shots, persistent capture reuse, and hard-cancel through `/api/v1/capture/stop` have passed on a Raspberry Pi.
- `zwo`: initial ZWO ASI adapter using the native `libASICamera2` SDK library. On Debian/Raspberry Pi OS trixie, install the `libasi` package.
- `gphoto2`, `v4l2`, `indi`, `custom_command`: extension points with API-visible errors until fully implemented.

The browser never calls camera commands directly. All camera actions go through `/api/v1` and the backend adapter interface.

ZWO support is intentionally not a mock. Without `libASICamera2.so`, detection returns no ZWO cameras and capabilities include an install hint. Real ZWO hardware validation is still pending.
