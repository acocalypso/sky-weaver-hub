# Raspberry Pi

Recommended hardware:

- Raspberry Pi 4 or 5
- Raspberry Pi OS Bookworm 64-bit
- HQ Camera IMX477, Camera Module 3 IMX708, or libcamera-compatible Arducam

Camera detection uses `rpicam-hello --list-cameras` or `libcamera-hello --list-cameras`. Capture uses `rpicam-still` or `libcamera-still`.

OV5647 Camera Module v1 is possible but has exposure limitations; use clear warnings in production setup.

## Verified Hardware

- Raspberry Pi 3 Model B Rev 1.2, aarch64, Debian GNU/Linux 13/trixie.
- IMX290 libcamera-compatible camera detected as `imx290 [1920x1080 12-bit RGGB]`.
- The `skyweaver` service user can list the camera after install/upgrade camera group provisioning.
- API rpicam test shots passed before service restart, after `skyweaver.target` restart, and after controlled reboot on 2026-06-24.
- API stop hard-cancel passed on an IMX290 60s rpicam capture on 2026-06-24: the final capture job was `canceled` with `stop_mode: hard_cancel`, adapter method `terminate`, and no leftover rpicam/libcamera process.
