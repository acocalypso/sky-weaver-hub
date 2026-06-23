# Raspberry Pi

Recommended hardware:

- Raspberry Pi 4 or 5
- Raspberry Pi OS Bookworm 64-bit
- HQ Camera IMX477, Camera Module 3 IMX708, or libcamera-compatible Arducam

Camera detection uses `rpicam-hello --list-cameras` or `libcamera-hello --list-cameras`. Capture uses `rpicam-still` or `libcamera-still`.

OV5647 Camera Module v1 is possible but has exposure limitations; use clear warnings in production setup.
