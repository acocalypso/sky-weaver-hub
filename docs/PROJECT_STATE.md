# Sky Weaver Hub Project State

Last updated: 2026-06-24

This document tracks the current implementation state against the all-sky platform prompt. It is intended to be updated after each implementation phase.

## Current Summary

Sky Weaver Hub has moved from a mock dashboard toward a local-first Raspberry Pi/Linux all-sky platform. The repository now has a FastAPI backend, SQLite persistence, a camera adapter interface, mock capture with real image artifacts, an initial Raspberry Pi camera adapter, a daemon-owned scheduled capture loop, API-key authentication, systemd and installer scaffolding, and a React UI wired to the local API.

The product is not yet Allsky feature-complete. The main missing areas are full image-product generation, public sky page, overlay/module workflows, remote upload execution, complete Allsky import, and broader camera adapter coverage beyond Raspberry Pi libcamera hardware.

## Repo Map

| Area | Current State |
| --- | --- |
| Frontend | Vite, React 19, TypeScript, shadcn/Radix UI, Tailwind 4 via the official Vite plugin, with the existing Tailwind config loaded explicitly for theme compatibility. |
| Backend | FastAPI under `backend/skyweaver`, OpenAPI docs at `/api/docs`, REST API under `/api/v1`. |
| Database | SQLite via stdlib `sqlite3`, schema seeded in `backend/skyweaver/db.py`. No external database dependency. |
| Storage | Local filesystem storage for images, thumbnails, products, logs, and config. Dev defaults are local paths; system install targets `/var/lib/skyweaver`, `/etc/skyweaver`, `/var/log/skyweaver`. |
| Auth | Local admin JWT login plus hashed API keys with scopes. Installer can seed a configured admin password hash during first setup, and the app now enforces guided setup completion before normal admin use, including bootstrap-password detection and stronger password guidance. |
| Camera abstraction | `CameraAdapter` base class plus working `mock` adapter and initial `rpicam`/`libcamera` adapter. Other adapters are placeholders with actionable errors. |
| UI/API integration | Dashboard, Cameras, Schedule, Gallery, Night Products, Logs, Settings, API Keys, and Developer API call the local backend. |
| Deployment | `install.sh`, `upgrade.sh`, `uninstall.sh`, `support.sh`, and systemd units exist. Fresh interactive installs prompt for first-setup values. |
| Tests | Backend pytest coverage for health/status, login, API keys, mock capture, first-setup hardening, system service controls, scheduled daemon capture, queued test/single/sequence capture execution, pause/resume/stop queue semantics, schedule preview, daemon heartbeat/activity, interrupted job recovery, mock overnight acceptance flow, night product generation, migration preview, and mock adapter. Frontend component tests cover Dashboard, Gallery, Health, Settings, API Keys, and first setup. Shell tests cover installer dry-run, service-control sudoers generation, and repeat-install idempotency with mocked system commands. |

## Implemented Capabilities

### Backend/API

- `/api/v1/health`
- `/api/v1/status`
- `/api/v1/system/metrics`
- `/api/v1/system/services`
- `/api/v1/system/services/{name}` for per-service `systemctl show` detail and recent `journalctl` output when available
- `/api/v1/system/services/{name}/{action}` for allowlisted start/stop/restart controls
- `/api/v1/system/diagnostics`
- `/api/v1/logs`
- `/api/v1/auth/login`
- `/api/v1/auth/logout`
- `/api/v1/auth/me`
- User CRUD endpoints
- API key list/create/patch/delete
- Camera list/detect/create/get/patch/delete/capabilities/settings-schema/test
- Settings get/patch
- Camera profiles get/create/get/patch/delete
- Capture state/start/stop/pause/resume/test-shot/single/sequence/jobs
- Schedule get/put/preview/recalculate
- Image list/latest/detail/download/delete/reprocess/days/day
- Products list/detail/queue/download
- Dark frame placeholder endpoints
- Module and module-flow placeholder endpoints
- Remote target placeholder endpoints
- Allsky migration detect/preview/import/job endpoints
- Server-Sent Events at `/api/v1/events/stream`
- Standard success/error envelope shape

### Camera and Capture

- Mock camera generates synthetic all-sky images.
- Mock capture writes:
  - original image
  - metadata JSON sidecar
  - thumbnail
  - SQLite image row
  - capture job row
  - capture state update
  - realtime event
- `rpicam`/`libcamera` adapter can detect and capture through command-line tools when available.
- Subprocess calls use argv lists instead of shell string interpolation.

### Capture Daemon

- `backend/skyweaver/capture_daemon.py` now owns a scheduled capture loop.
- The daemon checks capture state, honors the configured interval, claims pending capture jobs, and runs scheduled captures through the shared capture service.
- Scheduled captures now consult the configured active window before creating unattended jobs.
- A daemon lock file prevents duplicate daemon loops from running in the same data directory.
- The daemon writes a heartbeat, PID, last claimed job, and last success timestamp into `capture_state`; `/api/v1/system/services` reports running/stale status and recent daemon activity.
- Test-shot, queued single, queued sequence, and scheduled captures now run through daemon-owned capture jobs and share the same capture execution path.
- `/api/v1/capture/single` creates a persistent pending capture job for daemon execution.
- `/api/v1/capture/sequence` creates a persistent parent job that the daemon expands into child capture artifacts.
- Pause holds queued automation capture jobs, resume releases them, test-shot jobs still run for manual verification, and stop cancels pending/claimed queued capture jobs while recording best-effort cancel intent for in-progress exposures. The rpicam/libcamera adapter can terminate its active capture subprocess from inside the daemon process; adapters without hard-cancel support still finish gracefully.
- Capture daemon startup requeues interrupted claimed/running capture jobs after service restart.
- `/api/v1/schedule/preview-tonight` returns a real active window and next transition for fixed or sun-angle schedules.
- Backend tests verify daemon-run scheduled capture creation, interval gating, queued test-shot completion while automation is stopped, queued single-capture completion, queued sequence completion, graceful stop reporting, best-effort hard-cancel intent, adapter hard-cancel handling, pause/resume/stop semantics, schedule preview, heartbeat/activity reporting, interrupted job recovery, and a mock overnight flow that checks latest/gallery updates.

### Frontend

- Local login page.
- First-setup page that blocks normal admin routes until observatory details, timezone, primary camera, public page mode, and bootstrap password status are confirmed. It detects hardware camera candidates, warns when only mock capture is available, and shows live password readiness guidance.
- Dashboard with latest image, start/pause/resume/stop/test-shot controls, queued single/sequence capture controls, capture job progress, daemon activity, status, metrics, and recent captures.
- Cameras page with detection, adapter selection, night-profile editing, and test shot.
- Schedule page with sun-angle/fixed/manual mode settings.
- Schedule page displays the backend active window, next transition, and fixed-time controls.
- Dashboard Tonight panel displays capture-window status and the next schedule transition.
- Gallery page with day/mode/quality filters and image detail.
- Night Products page queues product jobs, shows processing job progress, and lists generated downloads.
- System Health page shows metrics, service status, start/stop/restart actions, per-service detail/journal output, queue counts, recent logs, and diagnostics JSON export.
- Logs page reads backend logs.
- Settings page edits local settings groups.
- API Keys page creates scoped keys, shows full key once, enables/disables, and revokes.
- Developer API page includes core endpoints and curl/JavaScript/Python examples.

### Installer/Operations

- `skyweaver.target`
- `skyweaver-api.service`
- `skyweaver-capture.service`
- `skyweaver-worker.service`
- Installer creates directories, system user, Python venv, frontend build, config, and services.
- Installer grants the `skyweaver` service user available camera hardware groups and systemd supplementary groups for Pi camera access.
- Installer and upgrade grant the `skyweaver` service user constrained sudoers permissions for Sky Weaver `systemctl` start/stop/restart controls only.
- Installer dry-run no longer requires root or writes config, and CI has a temp-dir test harness for dry-run and repeat-install idempotency.
- Fresh interactive installer setup asks for admin credentials, observatory location/timezone, primary camera adapter, and public page mode; noninteractive installs use defaults or explicit environment values.
- Full installer, repeat-install, service restart, reboot, and IMX290 rpicam capture acceptance passed on a Raspberry Pi 3 Model B running Debian 13/trixie.
- Upgrade script backs up config/database and rebuilds.
- Uninstall script removes services and optionally data.
- Support script collects OS, camera, service, journal, disk, config-redacted, and API health details.

### Processing Worker

- `backend/skyweaver/worker.py` now claims and executes pending processing jobs.
- Thumbnail reprocess jobs regenerate thumbnails for existing image rows.
- Keogram jobs generate a real JPEG night product from same-day image center columns.
- Timelapse jobs generate downloadable MP4/WebM night products through `ffmpeg`.
- Mini timelapse jobs generate sampled lower-resolution MP4/WebM night products.
- Startrail jobs generate downloadable JPEG night products through lighten blending.
- Completed keograms, timelapses, mini timelapses, and startrails are inserted into `night_products` and are downloadable through `/api/v1/products/{id}/download`.
- `/api/v1/processing/jobs` exposes queued/running/completed processing jobs for UI progress.
- Worker startup requeues interrupted claimed/running processing jobs after service restart.
- Backend tests verify keogram, timelapse, mini timelapse, and startrail product generation from mock captures.

### Documentation

- README updated with architecture, quickstart, API examples, status, and limitations.
- Dedicated docs exist for install, upgrade, uninstall, Raspberry Pi, cameras, API, mobile API, Allsky migration, plugin development, security, and troubleshooting.
- Agent guidelines and a reusable task template define the Planner -> Engineer -> Developer -> Reviewer workflow and Sky Weaver-specific implementation rules.

## Phase Status

| Phase | Status | Notes |
| --- | --- | --- |
| Phase 0: Repo inspection | Done | React/Vite Lovable-style frontend identified; Supabase flow replaced by local API direction. |
| Phase 1: API skeleton and SQLite | Mostly done | Backend, schema, health/status, API client, core routes, and mock capture exist. Dedicated migration framework still needed. |
| Phase 2: Auth/API keys/settings/docs | Mostly done | JWT login, API-key scopes, settings, API Keys UI, Developer API UI, installer-seeded first setup values, in-app first-setup enforcement, bootstrap-password detection, password-strength guidance, and in-process rate limiting for failed login/setup completion attempts exist. Broader audit trails remain open. |
| Phase 3: Camera adapters and test shot | Partial | Mock and rpicam/libcamera implemented and validated with an IMX290 on Raspberry Pi. ZWO, gPhoto2, V4L2, INDI, custom command are placeholders. |
| Phase 4: Capture daemon and realtime | Partial | Scheduled daemon loop, shared capture service, persistent job claiming for test/single/scheduled/sequence captures, graceful stop reporting, best-effort rpicam hard-cancel wiring, pause/resume/stop queue semantics, active-window checks and UI preview, interval gating, lock-file duplicate-loop guard with stale lock recovery, heartbeat/activity reporting, interrupted job recovery, SSE endpoint, Pi reboot service startup acceptance, and IMX290 capture after restart/reboot acceptance exist. Real-Pi hard-cancel acceptance is still open. |
| Phase 5: Image storage/gallery/latest/metadata | Partial | Mock capture artifacts, metadata, thumbnails, image rows, gallery, latest image exist. Latest symlink/copy and broader metadata extraction are open. |
| Phase 6: Processing worker/products/retention | Partial | Worker claims jobs, thumbnail reprocess exists, keogram JPEG generation, ffmpeg timelapse/mini-timelapse generation, and startrail generation exist, and product job progress is visible in the UI. Cleanup and upload execution are open. |
| Phase 7: Overlay/modules | Early scaffold | Module tables/endpoints exist. Overlay editor, processor, built-in modules, safe module execution are open. |
| Phase 8: Installer/systemd/support/docs | Partial | Scripts and units exist. Shellcheck CI, installer dry-run/idempotency tests, service-control sudoers generation, interactive first-setup prompts, real Pi install, repeat install, service restart, and reboot verification exist. Nginx option and broader Pi camera verification are open. |
| Phase 9: Allsky migration/remote upload | Early scaffold | Detection and dry-run count preview exist. Real import, rollback, unsupported-setting report, and remote upload execution are open. |
| Phase 10: Polish/mobile/tests/hardening | Partial | Mobile API docs, latest/status/gallery endpoints, route bundle splitting, system health diagnostics/service detail UI, initial frontend component tests, and CI workflow exist. Broader tests, UX polish, performance, and security hardening remain. |

## Open Topics

### Highest Priority

- Expand the capture daemon into complete queue ownership:
  - validate rpicam hard-cancel behavior on Raspberry Pi hardware
  - keep documenting and surfacing in-progress capture stop limits clearly
- Keep schedule preview and daemon state visible across Dashboard and Schedule as the daemon model evolves.
- Complete mock acceptance flow end to end:
  - run longer manual/dev overnight simulations outside pytest
  - validate behavior with real service restarts
- Harden first-run setup:
  - expand audit detail around repeated setup/login failures

### Raspberry Pi Deployment

- Test `install.sh` on fresh Raspberry Pi OS Bookworm 64-bit; Raspberry Pi 3 Model B on Debian 13/trixie has passed install/repeat-install/service-restart/reboot acceptance.
- Expand interactive setup as new deployment options are added.
- Add explicit Raspberry Pi model and Bookworm detection messages.
- Add camera presence check during install.
- Add optional nginx reverse proxy.
- Add `skyweaver` convenience command or documented aliases for start/stop/restart/status.
- Keep shellcheck coverage passing as installer scripts evolve.
- Expand installer tests when interactive setup and nginx options are added.
- Continue confirming service permissions and ownership on real Pi as more camera and upload paths are added.

### Camera Hardware

- Expand `rpicam`/`libcamera` adapter:
  - AWB controls
  - quality/compression
  - tuning file
  - rotation/flip/crop/resize where supported
  - capture command compatibility across Bookworm naming
  - better parsing of camera list output
- Implement V4L2/webcam capture through ffmpeg or OpenCV.
- Implement gPhoto2 detection/capture for DSLR/mirrorless.
- Define ZWO SDK boundary and detection failure messages.
- Add INDI adapter skeleton with expected integration contract.
- Design custom command adapter with explicit security controls and sandbox warnings.

### Image Pipeline

- Add latest image symlink or copy publisher.
- Add EXIF/basic metadata extraction.
- Add image resize/crop/stretch processing.
- Add configurable bad image thresholds.
- Add dark-frame capture and median combine.
- Add dark-frame matching by exposure/gain/temperature/camera.
- Add overlay rendering with variables.
- Add star count placeholder or simple implementation.
- Add cloud score placeholder or simple heuristic.

### Night Products

- Expand keogram generation options and UI progress.
- Expand product progress reporting with detailed per-frame/per-stage progress.
- Add regenerate by date/date range.
- Add download-ready UI states.
- Add skip bad/overexposed image rules.

### Web UI

- Add public sky page without login.
- Add capture control page separate from dashboard.
- Add image detail route.
- Add overlay editor.
- Add module/plugin manager.
- Add dark frames page.
- Add remote upload page.
- Expand system health journal/service detail views with richer failure analysis and unit history.
- Add Allsky migration page.
- Add deployment/installer docs page.
- Improve mobile layouts after real data flows are in place.
- Route-level bundle splitting is enabled; keep watching bundle size as large pages and dependencies are added.

### API and Mobile Readiness

- Add cursor pagination where useful.
- Expand filters:
  - date range
  - camera
  - mode
  - product type
  - bad image
  - processing status
- Add Swift/Kotlin response examples.
- Expand generated OpenAPI artifact checks beyond upload-only validation.
- Add websocket endpoint if SSE is insufficient.
- Ensure public endpoints are explicitly unauthenticated and admin endpoints are protected.

### Security

- Remove any permanent reliance on bootstrap `admin / skyweaver-change-me`.
- Expand first-setup enforcement audit logging around password/login rate limits.
- Add broader auth audit logging for lockouts and repeated failures.
- Add CSRF protection if cookie auth is introduced.
- Add better secret handling for remote targets.
- Redact all secrets in diagnostics and logs.
- Add file permission checks for config and database.
- Review all subprocess calls and future custom-command execution for injection risk.
- Add API-key scope tests for every protected endpoint group.

### Allsky Migration

- Implement real import of:
  - images
  - timelapses
  - keograms
  - startrails
  - dark frames
  - selected settings
  - location
  - camera hints
  - overlay assets where possible
- Add unsupported setting report.
- Add import log and UI progress.
- Add rollback of Sky Weaver-created rows/files only.
- Keep original Allsky data untouched.

### Remote Upload

- Add remote target config UI.
- Implement local public website mode.
- Implement SFTP/SCP/rsync/FTP where feasible.
- Add upload retry queue.
- Add upload logs.
- Redact credentials everywhere.

### Plugin/Module System

- Define Python module contract in code.
- Add built-in module registry.
- Add built-in modules:
  - thumbnail
  - overlay
  - bad image detector
  - dark frame subtraction
  - star counter placeholder
  - remote upload
  - latest image publisher
  - metadata writer
- Add flow execution ordering.
- Add timeout and failure behavior.
- Keep uploaded custom modules disabled by default.

### Database and Migrations

- Replace ad hoc `CREATE TABLE IF NOT EXISTS` initialization with versioned migrations.
- Add schema version tracking.
- Add migration command for upgrades.
- Add backup/restore validation.
- Consider indexes for images, jobs, logs, events, day_key, and created_at.

### Testing and CI

- Add frontend route smoke tests.
- Expand component tests beyond Dashboard, Settings, Gallery, and API Keys.
- Add public page no-auth test once implemented.
- Add admin route auth tests.
- Add backend tests for:
  - schedule calculation
  - settings validation
  - image database CRUD
  - processing job lifecycle
  - every API-key scope boundary
- Expand GitHub Actions after Pi validation:
  - installer tests for future interactive setup and nginx paths
  - real migration fixture tests
  - OpenAPI diff checks

## Known Current Limitations

- Capture daemon now performs scheduled captures and consumes queued test-shot, single-capture, and sequence jobs. Graceful stop fallback, best-effort rpicam hard-cancel wiring, pause/resume/stop queue semantics, daemon activity visibility, Dashboard capture job progress, and interrupted job requeue on service start exist; Raspberry Pi reboot and IMX290 capture-after-reboot acceptance have passed, but rpicam hard-cancel still needs real-hardware validation.
- Worker now generates thumbnails, keograms, ffmpeg timelapses, mini timelapses, and startrails, but retention cleanup and upload execution are still open.
- Product endpoints queue jobs; keogram, timelapse, mini timelapse, and startrail currently produce downloadable night products.
- Public page is not implemented.
- Remote upload is not implemented.
- Allsky migration does not yet import data.
- API server no longer performs camera capture inline for test shots; test-shot requests enqueue daemon-owned `test` jobs so manual verification still works while automation is stopped.
- Tailwind 4 is enabled through the official Vite plugin while preserving the existing theme config and shadcn animation utilities.
- Lint passes with warnings from existing generated UI/hook patterns.
- Real Raspberry Pi install, service restart, reboot, and IMX290 real-camera capture acceptance passed on a Raspberry Pi 3 Model B running Debian 13/trixie.

## Recent Verification

Most recent checks run during implementation:

- `npm run build`: passed
- `npm test`: passed with 6 tests
- `npm run lint`: passed with zero warnings
- `npm audit --audit-level=high`: passed with 0 vulnerabilities
- `backend\\.venv\\Scripts\\python -m pytest backend\\tests`: passed with 22 tests

Most recent local follow-up checks on 2026-06-24:

- `npm run lint`: passed
- `npm test`: passed with 7 tests
- `npm run build`: passed
- `backend\\.venv\\Scripts\\python -m pytest backend\\tests`: passed with 39 tests
- Local OpenAPI generation plus `python -m json.tool artifacts\\openapi.json`: passed
- `shellcheck install.sh scripts/test_install.sh upgrade.sh uninstall.sh support.sh`: not run locally because ShellCheck is not installed on this Windows host; CI installs ShellCheck on Ubuntu.

Raspberry Pi acceptance on 2026-06-23:

- Host: Raspberry Pi 3 Model B Rev 1.2, aarch64, Debian GNU/Linux 13/trixie.
- `/home/pi/sky-weaver-hub` fast-forwarded to `639dde2`.
- `sudo ./install.sh`: passed, including apt dependencies, backend venv, npm frontend build, config creation, systemd unit install, and target start.
- Repeat `sudo ./install.sh`: passed and preserved existing `/etc/skyweaver/skyweaver.env`.
- API smoke test: `/api/v1/health`, login, `/api/v1/status`, `/api/v1/capture/test-shot`, and `/api/v1/images/latest` passed.
- `systemctl restart skyweaver.target`: all Sky Weaver units returned active, API health passed, no failed units were listed, and restart counters were zero.
- Controlled Pi reboot: SSH returned, `skyweaver.target`, `skyweaver-api.service`, `skyweaver-capture.service`, and `skyweaver-worker.service` were active, no failed units were listed, API health passed, latest image persisted, and restart counters were zero.

Raspberry Pi IMX290 camera acceptance on 2026-06-24:

- `/home/pi/sky-weaver-hub` fast-forwarded to `43d24d6` and `sudo ./upgrade.sh` passed; `/etc/sudoers.d/skyweaver.tmp` parsed OK.
- Host still reports Raspberry Pi 3 Model B Rev 1.2, aarch64, Debian GNU/Linux 13/trixie.
- `rpicam-hello --list-cameras` detected `imx290 [1920x1080 12-bit RGGB]` as both `pi` and the `skyweaver` service user.
- API camera detection returned mock plus one `rpicam://0` IMX290 candidate; configured primary camera is `IMX290` using the `rpicam` adapter.
- API test shot before restart passed: `/var/lib/skyweaver/images/20260624/050752_5ba9cd3e.jpg`, 22013 bytes, and `/api/v1/images/latest` matched the new image ID.
- `/api/v1/system/services/skyweaver/restart` queued `skyweaver.target` restart; after services returned, API test shot passed: `/var/lib/skyweaver/images/20260624/050833_b71e0db4.jpg`, 22009 bytes, and latest image matched.
- Controlled Pi reboot: SSH and API returned, all Sky Weaver services were active, no failed units were listed, `skyweaver` still detected the IMX290, and API test shot passed: `/var/lib/skyweaver/images/20260624/051015_34ade951.jpg`, 21983 bytes, with latest image updated.

## Recommended Next Phase

The next development phase should focus on operational hardening, because interrupted job recovery and the initial night products now generate real downloadable artifacts.

Suggested next tasks:

1. Validate rpicam hard-cancel behavior on Raspberry Pi hardware and tune terminate/kill timing if needed.
2. Expand system health journal/service detail views with richer failure analysis and unit history.
3. Add richer audit logging around repeated setup/login failures.
