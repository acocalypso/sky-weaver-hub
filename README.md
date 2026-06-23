# Sky Weaver Hub

Sky Weaver Hub is a local-first, REST API first all-sky camera platform for Raspberry Pi and Linux. It is intended as a modern successor path for users who like the practical Allsky experience but want a cleaner backend, a modern responsive UI, API-key access for future mobile apps, and hardware adapters that keep camera commands out of the browser.

## Current Status

This repository now contains a working local-first platform slice:

- Vite/React admin UI using the local `/api/v1` service.
- FastAPI backend under `backend/` with SQLite storage.
- Bootstrap admin login, guided first-setup completion, and API-key ready auth model.
- Mock camera adapter that writes real images, thumbnails, metadata sidecars, image rows, capture jobs, logs, and realtime events.
- Raspberry Pi `rpicam-still` / `libcamera-still` adapter path.
- Versioned REST endpoints, OpenAPI docs at `/api/docs`, and SSE events at `/api/v1/events/stream`.
- Daemon-owned scheduled capture loop with queued single/sequence captures, pause/resume/stop queue semantics, heartbeat reporting, interrupted job recovery, and stale daemon lock recovery.
- Processing worker for thumbnail reprocess, keogram JPEGs, ffmpeg timelapses, mini timelapses, and startrail JPEGs.
- Systemd units and installer scripts for Pi deployment, with first-setup prompts and dry-run/idempotency tests.
- Allsky migration detection and dry-run preview endpoints. Real import is still scaffolded.

Some Allsky parity items are intentionally scaffolded for later phases: public unauthenticated sky page, remote upload execution, overlay editing, dark-frame median combine, full Allsky import, and custom module sandboxing.

## Supported Targets

Primary:

- Raspberry Pi 4 and Raspberry Pi 5
- Raspberry Pi OS Bookworm 64-bit
- Raspberry Pi HQ Camera IMX477
- Raspberry Pi Camera Module 3 IMX708
- Arducam libcamera-compatible cameras

Development and partial support:

- Raspberry Pi Zero 2 W with reduced processing
- Debian/Ubuntu Linux. A Raspberry Pi 3 Model B on Debian 13/trixie has passed install, repeat-install, service restart, reboot, API, and mock capture acceptance.
- Mock camera
- ZWO, gPhoto2, V4L2/webcam, INDI, and custom command adapters as extension points

## Raspberry Pi Quickstart

```bash
git clone https://github.com/acocalypso/sky-weaver-hub.git
cd sky-weaver-hub
sudo ./install.sh
```

After install:

- Admin UI: `http://skyweaver.local:8765/`
- Public page target: `http://skyweaver.local:8765/public`
- API docs: `http://skyweaver.local:8765/api/docs`
- Bootstrap login: `admin / skyweaver-change-me`

On first login, the admin UI requires setup completion so you can change the bootstrap password, confirm observatory location/timezone, choose the primary camera, and set public page mode before normal admin use.

The installer creates `/opt/skyweaver`, `/etc/skyweaver`, `/var/lib/skyweaver`, and `/var/log/skyweaver`, installs Node/npm and Python dependencies, grants the service user camera hardware groups, builds the frontend, installs systemd units, and starts `skyweaver.target`. On a fresh interactive install it asks for admin credentials, observatory location, timezone, primary camera adapter, and public page mode. Re-running the installer preserves the existing `/etc/skyweaver/skyweaver.env`.

To inspect installer actions without root or filesystem writes:

```bash
SKYWEAVER_DRY_RUN=1 ./install.sh
```

## Development

Run the backend:

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn skyweaver.main:app --reload --port 8765
```

Run the frontend:

```bash
npm install
npm run dev
```

The frontend talks to the same host by default. For a separate backend URL:

```bash
VITE_SKYWEAVER_API_BASE=http://127.0.0.1:8765 npm run dev
```

## API Examples

```bash
curl http://127.0.0.1:8765/api/v1/health
```

```bash
TOKEN=$(curl -s http://127.0.0.1:8765/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"username":"admin","password":"skyweaver-change-me"}' | jq -r .data.token)

curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/api/v1/status
curl -H "Authorization: Bearer $TOKEN" -X POST http://127.0.0.1:8765/api/v1/capture/test-shot \
  -H 'content-type: application/json' \
  -d '{"camera_id":null,"exposure_ms":1000,"gain":1,"format":"jpg"}'
```

JavaScript:

```js
fetch("http://skyweaver.local:8765/api/v1/images/latest", {
  headers: { Authorization: `Bearer ${apiKey}` },
});
```

Python:

```python
import requests

requests.get(
    "http://skyweaver.local:8765/api/v1/status",
    headers={"Authorization": f"Bearer {api_key}"},
)
```

## Service Commands

```bash
sudo systemctl start skyweaver.target
sudo systemctl stop skyweaver.target
sudo systemctl restart skyweaver.target
sudo systemctl status skyweaver.target
```

Individual services:

- `skyweaver-api.service`
- `skyweaver-capture.service`
- `skyweaver-worker.service`

## Verification

Common checks:

```bash
npm run lint
npm test
npm run build
backend/.venv/bin/python -m pytest backend/tests
bash scripts/test_install.sh
```

On Windows, use `backend\.venv\Scripts\python -m pytest backend\tests` for backend tests.

## Allsky Migration

Sky Weaver detects common Allsky directories such as `~/allsky`, `~/allsky-OLD`, `~/allsky-SAVED`, `/home/pi/allsky`, and `/var/www/html/allsky`. Current migration support provides detection, dry-run counts, and queued import jobs. Real import and rollback are still scaffolded. The original Allsky data is never deleted.

## Documentation

See `docs/` for install, upgrade, uninstall, camera, API, mobile API, plugin, security, migration, Raspberry Pi, and troubleshooting notes.
