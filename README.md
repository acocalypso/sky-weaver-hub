# Sky Weaver Hub

Sky Weaver Hub is a local-first, REST API first all-sky camera platform for Raspberry Pi and Linux. It is intended as a modern successor path for users who like the practical Allsky experience but want a cleaner backend, a modern responsive UI, API-key access for future mobile apps, and hardware adapters that keep camera commands out of the browser.

## Current Status

This repository now contains a working local-first platform slice:

- Vite/React admin UI using the local `/api/v1` service.
- FastAPI backend under `backend/` with SQLite storage and versioned schema migrations.
- Bootstrap admin login, guided first-setup completion, and API-key ready auth model.
- Mock camera adapter plus initial rpicam/libcamera and ZWO ASI camera support.
- Raspberry Pi `rpicam-still` / `libcamera-still` adapter path, validated with an IMX290 camera.
- Versioned REST endpoints, OpenAPI docs at `/api/docs`, and SSE events at `/api/v1/events/stream`.
- Daemon-owned scheduled capture loop with day/night profile selection, fixed/sun/twilight windows, restart-safe per-mode capture intervals, next-capture preview, latest-only unsaved captures, queued test/single/sequence captures, pause/resume/stop queue semantics, best-effort rpicam hard-cancel wiring, heartbeat reporting, interrupted job recovery, and stale daemon lock recovery.
- Processing worker for thumbnail reprocess, keogram JPEGs, ffmpeg timelapses, mini timelapses, and startrail JPEGs, with end-of-night product jobs queued from the nighttime profile.
- Built-in overlay module with editable lines, colors, placement controls, a trusted post-capture module flow, and external manifest registration; custom code uploads stay disabled until sandboxing/signing is implemented.
- Remote upload page and worker-backed filesystem target execution for latest images and generated products.
- Public unauthenticated sky page at `/public`, backed by stable latest-image artifacts and public latest/product API endpoints that honor the public-page enabled setting, including latest-only captures that are not saved to the gallery.
- System Health UI with service controls, per-service detail, recent journal output, diagnostics export, and queue/metric summaries.
- Systemd units and installer scripts for Pi deployment, with first-setup prompts, constrained service-control permissions, and dry-run/idempotency tests.
- Allsky migration detection, preview, worker-backed image/product import, selected settings import, rollback, and Migration UI. Original Allsky files are copied, never deleted.

Some Allsky parity items are intentionally scaffolded for later phases: SFTP/SCP/rsync/FTP upload targets, overlay live previews/presets, dark-frame median combine, full Allsky settings/dark-frame/overlay import, and custom module sandboxing.

## Supported Targets

Primary:

- Raspberry Pi 4 and Raspberry Pi 5
- Raspberry Pi OS Bookworm 64-bit
- Raspberry Pi HQ Camera IMX477
- Raspberry Pi Camera Module 3 IMX708
- Arducam libcamera-compatible cameras

Development and partial support:

- Raspberry Pi Zero 2 W with reduced processing
- Debian/Ubuntu Linux. A Raspberry Pi 3 Model B on Debian 13/trixie has passed install, repeat-install, service restart, reboot, API, mock capture, and IMX290 rpicam capture acceptance.
- Mock camera
- ZWO ASI cameras through the native SDK library from Debian `libasi`; real hardware validation is pending
- gPhoto2, V4L2/webcam, INDI, and custom command adapters as extension points

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

On first login, the admin UI requires setup completion so you can replace the bootstrap password, confirm observatory location/timezone, detect or choose the primary camera, and set public page mode before normal admin use.

When public page mode is disabled, `/public` shows a disabled state and `/api/v1/public/latest` plus public product endpoints return `403 Public page is disabled`. When enabled, `/public` can show the latest image plus completed keograms, startrails, timelapses, and mini timelapses within the configured public product day window.

The installer creates `/opt/skyweaver`, `/etc/skyweaver`, `/var/lib/skyweaver`, and `/var/log/skyweaver`, installs Node/npm and Python dependencies, grants the service user camera hardware groups, builds the frontend, installs systemd units, grants narrow sudoers permissions for Sky Weaver service controls, and starts `skyweaver.target`. On a fresh interactive install it asks for admin credentials, observatory location, timezone, primary camera adapter, and public page mode. Re-running the installer preserves the existing `/etc/skyweaver/skyweaver.env`.

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
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/api/v1/capture/jobs
```

JavaScript:

```js
const latest = await fetch("http://skyweaver.local:8765/api/v1/public/latest").then((res) => res.json());
const imageUrl = `http://skyweaver.local:8765${latest.data.download_url}`;
```

Public clients should handle `403 Public page is disabled` as an operator-controlled disabled state.

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

The admin Health page can start, stop, restart, inspect `systemctl show` details, and read recent `journalctl` output for the Sky Weaver units when systemd is available.

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

## Database Migrations

Sky Weaver uses stdlib SQLite with an internal migration registry. App startup runs pending migrations automatically after creating the baseline schema.

```bash
cd backend
python -m skyweaver.migrate status
python -m skyweaver.migrate upgrade
```

The migration command is idempotent and records applied versions in `schema_migrations`.

## Allsky Migration

Sky Weaver detects common Allsky directories such as `~/allsky`, `~/allsky-OLD`, `~/allsky-SAVED`, `/home/pi/allsky`, and `/var/www/html/allsky`. Current migration support provides detection, dry-run counts, unsupported-setting reporting, queued image/product import jobs, selected settings import, camera hints, and rollback of Sky Weaver-created rows/files plus restored settings snapshots. The original Allsky data is never deleted.

## Documentation

See `docs/` for install, upgrade, uninstall, camera, API, mobile API, plugin, security, migration, Raspberry Pi, agent guidelines, task templates, and troubleshooting notes.
