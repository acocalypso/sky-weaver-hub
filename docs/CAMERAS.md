# Cameras

Adapters:

- `mock`: generates synthetic all-sky images for development and CI.
- `rpicam` / `libcamera`: Raspberry Pi camera path via `rpicam-still` or `libcamera-still`; IMX290 test shots and hard-cancel through `/api/v1/capture/stop` have passed on a Raspberry Pi.
- `zwo`: initial ZWO ASI adapter. It prefers the native `libASICamera2` SDK when available and can fall back to the `camera-zwo-asi` package command line tools (`zwo-asi-print`, `zwo-asi-dump`, `zwo-asi-shot`) installed in the backend virtualenv.
- `gphoto2`, `v4l2`, `indi`, `custom_command`: extension points with API-visible errors until fully implemented.

The browser never calls camera commands directly. All camera actions go through `/api/v1` and the backend adapter interface.

ZWO support is intentionally not a mock. Without the native SDK or `camera-zwo-asi` tools, detection returns no ZWO cameras and capabilities include an install hint. Real ZWO hardware validation is still pending.

The CLI backend writes/updates `zwo_asi.toml` under `SKYWEAVER_ZWO_CONFIG_DIR` when configured, otherwise beside the capture output in a `.zwo` directory. It updates package-style `[controllables]` and `[roi]` entries for exposure, gain, cooling, target temperature, width, and height. Advanced CLI-only settings can be supplied through adapter settings as dotted TOML keys in `zwo_cli_config`.
