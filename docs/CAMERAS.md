# Cameras

Adapters:

- `mock`: generates synthetic all-sky images for development and CI.
- `rpicam` / `libcamera`: Raspberry Pi camera path via `rpicam-still` or `libcamera-still`; IMX290 test shots and hard-cancel through `/api/v1/capture/stop` have passed on a Raspberry Pi.
- `zwo`, `gphoto2`, `v4l2`, `indi`, `custom_command`: extension points with API-visible errors until fully implemented.

The browser never calls camera commands directly. All camera actions go through `/api/v1` and the backend adapter interface.
