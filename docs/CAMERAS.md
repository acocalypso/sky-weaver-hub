# Cameras

Adapters:

- `mock`: generates synthetic all-sky images for development and CI.
- `rpicam` / `libcamera`: Raspberry Pi camera path via `rpicam-still` or `libcamera-still`; detection parses sensor, device path, resolution, bit depth, Bayer order, and capture modes from `rpicam-hello --list-cameras`. IMX290 test shots, persistent capture reuse, one-shot fallback after persistent-session failures, and hard-cancel through `/api/v1/capture/stop` have passed on a Raspberry Pi.
- `zwo`: initial ZWO ASI adapter using the native `libASICamera2` SDK library. On Debian/Raspberry Pi OS trixie, install the `libasi` package.
- `gphoto2`, `v4l2`, `indi`, `custom_command`: extension points with API-visible errors until fully implemented.

The browser never calls camera commands directly. All camera actions go through `/api/v1` and the backend adapter interface.

Raspberry Pi `rpicam`/`libcamera` profiles support manual exposure/gain and automatic daytime operation. When `auto_exposure` is enabled Sky Weaver does not pass `--shutter`; when `auto_gain` is enabled it does not pass `--gain`; when `auto_white_balance` is enabled it passes the selected rpicam AWB mode instead of fixed red/blue gains. Fixed manual values remain available for night captures and repeatable dark-frame calibration.

ZWO support is intentionally not a mock. Without `libASICamera2.so`, detection returns no ZWO cameras and capabilities include an install hint. Real ZWO hardware validation is still pending.
