# Sky Weaver Hub

Sky Weaver Hub is a local-first, REST API first all-sky camera platform for Raspberry Pi and Linux. It is intended as a modern successor path for users who like the practical Allsky experience but want a cleaner backend, a modern responsive UI, API-key access for future mobile apps, and hardware adapters that keep camera commands out of the browser.

## Current Status

Status reviewed on 2026-10-16 against source commit `1db48f4`. See [Project State](docs/PROJECT_STATE.md) for implementation and validation evidence.

This repository now contains a working local-first platform slice:

- Vite/React 19 admin UI using the local `/api/v1` service, Tailwind 4, shadcn/Radix UI, responsive operator pages, and click-to-open help on configuration controls.
- FastAPI backend under `backend/` with SQLite storage and versioned schema migrations.
- Bootstrap admin login, guided first-setup completion, API-key scopes, auth audit logs, and local-only admin operation.
- Mock camera adapter plus rpicam/libcamera and initial native ZWO ASI camera support through `libASICamera2`.
- Raspberry Pi `rpicam-still` / `libcamera-still` adapter path, validated with an IMX290 camera, including persistent signal-mode capture with one-shot fallback.
- Versioned REST endpoints, OpenAPI docs at `/api/docs`, and SSE events at `/api/v1/events/stream`.
- Daemon-owned scheduled capture loop with day/night profile selection, fixed/sun/twilight windows, restart-safe per-mode capture intervals, next-capture preview, latest-only unsaved captures, queued test/single/sequence captures, pause/resume/stop queue semantics, best-effort rpicam hard-cancel wiring, heartbeat reporting, interrupted job recovery, and stale daemon lock recovery.
- Dark-frame calibration with daemon-owned dark-frame set capture, median master generation, camera/settings-specific matching, manual active selection, and capture-time subtraction before downstream processing.
- Processing worker for thumbnail reprocess, keogram JPEGs, ffmpeg timelapses, mini timelapses, and startrail JPEGs, with end-of-night product jobs queued from the nighttime profile.
- Built-in overlay module with editable lines, colors, placement controls, a trusted post-capture module flow, and external manifest registration; custom code uploads stay disabled until sandboxing/signing is implemented.
- Remote upload page and worker-backed filesystem, rsync-over-SSH, SCP-over-SSH, SFTP-over-SSH, FTP, and FTPS target execution for latest images and generated products. Remote target secrets are stored in a local encrypted envelope and redacted from API responses/logs.
- Public unauthenticated sky page at `/public`, backed by stable latest-image artifacts and public latest/product API endpoints that honor the public-page enabled setting, including latest-only captures that are not saved to the gallery.
- Settings UI for observatory/storage/public/API/processing options, image/product retention cleanup, dark-frame management, browser-to-Pi time sync for offline Pis without RTC, and NetworkManager Wi-Fi scan/connect.
- System Health UI with service controls, per-service detail, recent journal output, failure analysis, diagnostics export, and queue/metric summaries.
- Systemd units and installer scripts for Pi deployment, with first-setup prompts, constrained service-control/time-sync/Wi-Fi permissions, dry-run/idempotency tests, and upgrade skips for unchanged Python/npm dependency manifests.
- Allsky migration detection, preview, worker-backed image/product/dark-frame/overlay-asset import, selected settings/profile import, basic overlay text import, rollback, and Migration UI. Original Allsky files are copied, never deleted.

Important remaining gaps include automatic upload triggers, scheduled retention/low-space protection, observing-night product windows, rolling mini timelapses, shared image transforms/masks, visual/image overlays, temperature-aware dark-frame matching, executable external module flows, sensors/charts/integrations, general backup/restore, and broader hardware/field validation. Product progress reporting already exists.

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
- ZWO ASI cameras through the native SDK library from Debian `libasi` or a vendor SDK install; fake-SDK tests exist, real ZWO hardware validation is pending
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

The installer creates `/opt/skyweaver`, `/etc/skyweaver`, `/var/lib/skyweaver`, and `/var/log/skyweaver`, installs Node/npm and Python dependencies, grants the service user camera hardware groups, builds the frontend, installs systemd units, grants narrow sudoers permissions for Sky Weaver service controls, browser time sync, and NetworkManager Wi-Fi actions, and starts `skyweaver.target`. On a fresh interactive install it asks for admin credentials, observatory location, timezone, primary camera adapter, and public page mode. Re-running the installer preserves the existing `/etc/skyweaver/skyweaver.env`.

`upgrade.sh` backs up config/database state, refreshes the install, and restarts `skyweaver.target`. It skips backend `pip install` when `backend/requirements.txt` is unchanged and the virtualenv is usable, and skips frontend `npm ci` when `package.json` plus `package-lock.json` are unchanged and `node_modules` exists. Use `SKYWEAVER_FORCE_PIP_INSTALL=1` or `SKYWEAVER_FORCE_NPM_INSTALL=1` to force dependency reinstall.

To inspect installer actions without root or filesystem writes:

```bash
SKYWEAVER_DRY_RUN=1 ./install.sh
```

## Docker / Compose

Docker runs the API/web UI, capture daemon and worker as separate services with persistent volumes. AMD64 and ARM64 images are published to `ghcr.io/acocalypso/sky-weaver-hub` by GitHub Actions.

Copy `.env.docker.example` to `.env`, set a random `SKYWEAVER_SECRET_KEY` (at least 32 characters) and a strong `SKYWEAVER_ADMIN_PASSWORD`, then run:

```bash
docker compose pull
docker compose up -d --no-build --wait
```

Open `http://localhost:8765` and complete setup. Mock capture works by default; real cameras need host-specific devices and libraries. See [Docker deployment](docs/DOCKER.md) for local builds, upgrades, storage, camera requirements and image publishing.

## Development

Use Python 3.11+ and Node.js 22.x (22.22.2+), 24.x (24.15+), or 26+ as allowed by `package.json` (Node 24 is used in CI). OS-provided Node packages can be older; check `node --version` before installing or building. See [dependency maintenance](docs/DEPENDENCIES.md) for the current upgrade decisions and compatibility exceptions.

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

The admin Health page can start, stop, restart, inspect `systemctl show` details, read recent `journalctl` output, and show capture/worker heartbeat plus recent job activity for the Sky Weaver units when systemd is available.

## Offline and Network Behavior

Sky Weaver is designed to keep core all-sky operation local. Once installed, capture, scheduling, local dashboard/API, public LAN page, dark-frame calibration, processing products, gallery, and local filesystem storage do not require internet access.

Network-dependent features are explicit and optional:

- Remote upload targets use the configured filesystem/SSH/FTP destination and can fail independently of capture if the destination is unreachable.
- Wi-Fi scan/connect requires NetworkManager and Wi-Fi hardware, but not internet access.
- Browser-to-Pi time sync uses the browser clock and does not require NTP.
- Installer and upgrade dependency downloads require package/network access unless dependencies are already available.

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

Sky Weaver detects common Allsky directories such as `~/allsky`, `~/allsky-OLD`, `~/allsky-SAVED`, `/home/pi/allsky`, and `/var/www/html/allsky`. Current migration support provides detection, dry-run counts, unsupported-setting reporting, queued image/product/dark-frame/overlay-asset import jobs, selected settings/profile import, basic overlay text import, camera hints, and rollback of Sky Weaver-created rows/files plus restored settings snapshots. The scanner imports recognized capture/product/dark-frame paths and excludes Allsky web, documentation, config, and overlay asset trees from gallery imports; overlay image assets are preserved separately for future overlay tooling. The original Allsky data is never deleted.

## Current Limitations

- Real outdoor overnight image quality and environmental stability still need more field validation.
- ZWO ASI support is adapter-backed but still needs real hardware validation in this environment.
- gPhoto2, V4L2/webcam, INDI, and custom command adapters are extension points, not complete camera support.
- Imported Allsky overlay image assets are preserved, but rendering those assets in Sky Weaver overlays is future work.
- Custom module code upload/execution remains disabled until sandboxing/signing is designed.
- Remote uploads are optional worker jobs; unreachable remote targets can delay upload processing until their timeouts expire.
- Uploads and failed-upload retries require explicit API/UI actions; capture/product completion does not automatically queue publication.
- Image/product retention cleanup is available through explicit API/UI actions. There is no scheduled cleanup or enforced `min_free_gb` capture policy.
- Products select images by UTC calendar `day_key`, which can split a night crossing midnight. Mini timelapses sample a selected date; they do not continually rebuild from the latest N frames.
- Shared post-capture resize/crop/stretch/mask processing is not implemented; rpicam capture controls and product frame resizing are narrower capabilities.
- General backup/export/restore, sensor control, historical charts, meteor detection, and optional integrations are not implemented.
- Temperature-aware dark-frame matching and richer calibration guidance remain future hardening.

## Documentation

See `docs/` for install, upgrade, uninstall, camera, API, mobile API, plugin, security, migration, Raspberry Pi, agent guidelines, task templates, and troubleshooting notes.

- [Current project state and verification](docs/PROJECT_STATE.md)
- [Dependency/runtime requirements and verification](docs/DEPENDENCIES.md)
- [Correctness fixes and regression coverage](docs/CORRECTNESS_REVIEW.md)
