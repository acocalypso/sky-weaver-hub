# Sky Weaver Hub Project State

Last updated: 2026-06-30

This document tracks the current implementation state against the all-sky platform prompt. It is intended to be updated after each implementation phase.

## Current Summary

Sky Weaver Hub has moved from a mock dashboard toward a local-first Raspberry Pi/Linux all-sky platform. The repository now has a FastAPI backend, SQLite persistence, a camera adapter interface, mock capture with real image artifacts, Raspberry Pi camera support, initial native ZWO ASI support, a daemon-owned scheduled capture loop, API-key authentication, systemd and installer support, and a React UI wired to the local API.

The product is not yet Allsky feature-complete. The main missing areas are longer real outdoor overnight soak validation, richer image-product options, full Allsky settings parity, overlay image rendering, dark-frame processing, and broader validated camera adapter coverage beyond Raspberry Pi libcamera hardware.

## Repo Map

| Area | Current State |
| --- | --- |
| Frontend | Vite, React 19, TypeScript, shadcn/Radix UI, Tailwind 4 via the official Vite plugin, with the existing Tailwind config loaded explicitly for theme compatibility. |
| Backend | FastAPI under `backend/skyweaver`, OpenAPI docs at `/api/docs`, REST API under `/api/v1`. |
| Database | SQLite via stdlib `sqlite3`, baseline schema seeded in `backend/skyweaver/db.py`, and versioned migrations tracked in `schema_migrations`. No external database dependency. |
| Storage | Local filesystem storage for images, thumbnails, products, logs, and config. Image/product delete and retention cleanup remove Sky Weaver-owned artifacts, sidecars, thumbnails, and matching latest artifacts. Dev defaults are local paths; system install targets `/var/lib/skyweaver`, `/etc/skyweaver`, `/var/log/skyweaver`. |
| Auth | Local admin JWT login plus hashed API keys with scopes. Installer can seed a configured admin password hash during first setup, and the app now enforces guided setup completion before normal admin use, including bootstrap-password detection, stronger password guidance, rate limiting, and local auth audit logs. |
| Camera abstraction | `CameraAdapter` base class plus working `mock` adapter, initial `rpicam`/`libcamera` adapter, and initial ZWO ASI adapter using the native `libASICamera2` SDK library from Debian `libasi` or a vendor SDK install. Other adapters are placeholders with actionable errors. |
| UI/API integration | Public Sky, Dashboard, Cameras, Schedule, Gallery, Night Products, Logs, Settings, API Keys, Modules, Remote Upload, Migration, Deployment, and Developer API call the local backend. |
| Deployment | `install.sh`, `upgrade.sh`, `uninstall.sh`, `support.sh`, and systemd units exist. Fresh interactive installs prompt for first-setup values. Installer/upgrade can provision Debian `libasi`, ZWO USB rules, and optional vendor SDK library support when ZWO is configured. Upgrade skips backend `pip install` when requirements are unchanged and the virtualenv exists. |
| Tests | Backend pytest coverage for health/status, login, auth audit logs, API keys, admin-route auth boundaries, settings validation, schedule calculation, mock capture, image/product/dark-frame delete and cleanup policy, retention cleanup, first-setup hardening, system service controls, scheduled daemon capture, day/night profile scheduling, latest-only unsaved captures, end-of-night product queuing, queued test/single/sequence capture execution, pause/resume/stop queue semantics, schedule preview, daemon heartbeat/activity, interrupted job recovery, mock overnight acceptance flow, night product generation, public product archive visibility including mini timelapses, filesystem, rsync-over-SSH, SCP-over-SSH, SFTP-over-SSH, FTP/FTPS upload execution/retry with encrypted target configs, Allsky migration preview/import/rollback/settings restore including dark frames, overlay assets, and camera profiles, module/overlay flows, external module manifests, mock adapter, and fake-SDK ZWO adapter behavior. Frontend component tests cover Public Sky latest/disabled/product archive/mobile-compact states, Dashboard, Gallery, Health, Settings, API Keys, Modules, Remote Upload, Migration, Deployment, and first setup, with route smoke coverage for public, auth, protected, and setup-required flows. Shell tests cover installer dry-run, service-control sudoers generation, and repeat-install idempotency with mocked system commands. |

## Implemented Capabilities

### Backend/API

- `/api/v1/health`
- `/api/v1/status`
- `/api/v1/system/metrics`
- `/api/v1/system/services`
- `/api/v1/system/services/{name}` for per-service `systemctl show` detail, recent `journalctl` output, failure analysis, and unit history when available
- `/api/v1/system/services/{name}/{action}` for allowlisted start/stop/restart controls
- `/api/v1/system/diagnostics`
- `/api/v1/logs`
- `/api/v1/auth/login`
- `/api/v1/auth/logout`
- `/api/v1/auth/me`
- Local auth audit logging for failed login/setup attempts, rate-limit blocks, and login recovery after previous failures
- User CRUD endpoints
- API key list/create/patch/delete
- Camera list/detect/create/get/patch/delete/capabilities/settings-schema/test
- Settings get/patch
- Camera profiles get/create/get/patch/delete
- Capture state/start/stop/pause/resume/test-shot/single/sequence/jobs
- Schedule get/put/preview/recalculate
- Image list/latest/detail/download/delete/reprocess/days/day and retention cleanup
- Public latest and public product metadata/download/thumbnail endpoints gated by `public_page.enabled`
- Products list/detail/queue/download/delete and retention cleanup
- Dark-frame list/delete endpoints; capture and processing/subtraction are still planned
- Module and module-flow endpoints, with a trusted built-in overlay module, trusted post-capture flow, external manifest registration, and custom code uploads still disabled
- Remote target, upload queue, upload retry, and upload job detail endpoints
- Allsky migration detect/preview/import/job endpoints
- Server-Sent Events at `/api/v1/events/stream`
- Standard success/error envelope shape

### Camera and Capture

- Mock camera generates synthetic all-sky images.
- Captures write:
  - original image
  - metadata JSON sidecar
  - thumbnail
  - stable latest image, thumbnail, and metadata copies under the local data directory
  - SQLite image row
  - capture job row
  - capture state update
  - realtime event
- `rpicam`/`libcamera` adapter can detect and capture through command-line tools when available.
- `zwo` adapter can detect and capture through the native ZWO ASI SDK when `libASICamera2` is installed.
- Subprocess calls use argv lists instead of shell string interpolation.

### Capture Daemon

- `backend/skyweaver/capture_daemon.py` now owns a scheduled capture loop.
- The daemon checks capture state, selects day or night mode from the configured active window, honors restart-safe per-profile capture intervals from persisted scheduled job start times, claims pending capture jobs, and runs scheduled captures through the shared capture service.
- Daytime and nighttime profiles can independently enable/disable capture and saving; unsaved scheduled captures update stable latest artifacts without creating permanent gallery rows.
- Nighttime profiles can queue keogram, startrail, timelapse, and mini-timelapse jobs once when the daemon observes the night window ending.
- A daemon lock file prevents duplicate daemon loops from running in the same data directory.
- The daemon writes a heartbeat, PID, last claimed job, and last success timestamp into `capture_state`; `/api/v1/system/services` reports running/stale status and recent daemon activity.
- Test-shot, queued single, queued sequence, and scheduled captures now run through daemon-owned capture jobs and share the same capture execution path.
- `/api/v1/capture/single` creates a persistent pending capture job for daemon execution.
- `/api/v1/capture/sequence` creates a persistent parent job that the daemon expands into child capture artifacts.
- Pause holds queued automation capture jobs, resume releases them, test-shot jobs still run for manual verification, and stop cancels pending/claimed queued capture jobs while recording best-effort cancel intent for in-progress exposures. The rpicam/libcamera adapter can terminate its active capture subprocess from inside the daemon process; adapters without hard-cancel support still finish gracefully.
- Capture daemon startup requeues interrupted claimed/running capture jobs after service restart.
- `/api/v1/schedule/preview-tonight` returns a real active window, next transition, capture mode, interval, persisted last scheduled capture, and next capture due time for fixed, named twilight, sunrise/sunset, or independent start/end sun-altitude schedules.
- Successful captures publish stable local latest artifacts and unauthenticated public latest metadata/download endpoints when the public page is enabled.
- Completed keogram, startrail, timelapse, and mini-timelapse products can be exposed through public product endpoints within the configured `public_page.product_days` visibility window.
- Backend tests verify daemon-run scheduled capture creation, interval gating, latest-only unsaved day captures, end-of-night product queueing, queued test-shot completion while automation is stopped, queued single-capture completion, queued sequence completion, graceful stop reporting, best-effort hard-cancel intent, adapter hard-cancel handling, pause/resume/stop semantics, schedule preview, heartbeat/activity reporting, interrupted job recovery, schema migrations, and a mock overnight flow that checks latest/gallery updates.

### Frontend

- Local login page.
- Public Sky page at `/public` that displays the latest public image, compact responsive safe metadata, and available public night products without admin login or controls, and shows a disabled state when `public_page.enabled` is false.
- First-setup page that blocks normal admin routes until observatory details, timezone, primary camera, public page mode, and bootstrap password status are confirmed. It detects hardware camera candidates, warns when only mock capture is available, and shows live password readiness guidance.
- Dashboard with latest image, start/pause/resume/stop/test-shot controls, queued single/sequence capture controls, capture job progress, daemon activity, status, metrics, and recent captures.
- Cameras page with detection, adapter selection, day/night profile editing, per-mode capture/save/interval controls, end-of-night product toggles, and test shot.
- Schedule page with sun-angle/fixed/manual mode settings.
- Schedule page displays the backend active window, next transition, and fixed-time controls.
- Dashboard Tonight panel displays capture-window status and the next schedule transition.
- Gallery page with day/mode/quality filters, image detail, delete action, quality fields, and storage/EXIF metadata preview.
- Night Products page queues product jobs, shows processing job progress, and lists generated downloads with product deletion.
- System Health page shows metrics, service status, start/stop/restart actions, per-service detail/journal output, failure analysis, unit history, queue counts, recent logs, and diagnostics JSON export.
- Logs page reads backend logs.
- Settings page edits local settings groups and can run image/product retention cleanup using the configured retention period.
- API Keys page creates scoped keys, shows full key once, enables/disables, and revokes.
- Developer API page includes core endpoints and curl/JavaScript/Python examples.

### Installer/Operations

- `skyweaver.target`
- `skyweaver-api.service`
- `skyweaver-capture.service`
- `skyweaver-worker.service`
- Installer creates directories, system user, Python venv, frontend build, config, and services.
- Installer and upgrade provision Debian `libasi`, ZWO ASI USB udev rules, and optional `libASICamera2.so` installation from a provided SDK archive URL when the configured primary adapter is `zwo`.
- Upgrade skips backend `pip install` when `backend/requirements.txt` is unchanged and the existing virtualenv has `pip`; `SKYWEAVER_FORCE_PIP_INSTALL=1` forces reinstall.
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
- Completed keograms, timelapses, mini timelapses, and startrails are inserted into `night_products`, downloadable through `/api/v1/products/{id}/download`, and removable through product delete/retention cleanup.
- `/api/v1/processing/jobs` exposes queued/running/completed processing jobs for UI progress.
- Worker startup requeues interrupted claimed/running processing jobs after service restart.
- Backend tests verify keogram, timelapse, mini timelapse, and startrail product generation from mock captures.

### Modules And Overlays

- A trusted built-in overlay module is seeded as `builtin.overlay`.
- Admins can enable/disable the built-in overlay module and edit line templates, add/remove lines, choose text/background colors, and select nine overlay positions through the Modules UI.
- A trusted built-in post-capture module flow is seeded as `builtin.post_capture`.
- Admins can enable/disable the post-capture flow, validate its runnable modules, and control whether the built-in overlay participates in capture-time processing.
- Overlay text variables include observatory name, capture timestamp/date/time, mode, camera, exposure, gain, and sensor temperature.
- Enabled overlays render directly onto captured images before sidecar metadata, thumbnails, and latest artifacts are generated.
- Image rows and metadata record whether an overlay was applied.
- External module manifests can be registered, listed, and deleted, but they remain disabled/untrusted and cannot execute until a future sandbox/signing runtime is explicitly implemented.

### Documentation

- README updated with architecture, quickstart, API examples, status, and limitations.
- Dedicated docs exist for install, upgrade, uninstall, Raspberry Pi, cameras, API, mobile API, Allsky migration, plugin development, security, and troubleshooting.
- Agent guidelines and a reusable task template define the Planner -> Engineer -> Developer -> Reviewer workflow and Sky Weaver-specific implementation rules.

## Phase Status

| Phase | Status | Notes |
| --- | --- | --- |
| Phase 0: Repo inspection | Done | React/Vite frontend identified; local API direction established. |
| Phase 1: API skeleton and SQLite | Done | Backend, schema, health/status, API client, core routes, mock capture, SQLite schema version tracking, idempotent migrations, query indexes, and `python -m skyweaver.migrate` status/upgrade command exist. |
| Phase 2: Auth/API keys/settings/docs | Done | JWT login, API-key scopes, settings, API Keys UI, Developer API UI, installer-seeded first setup values, in-app first-setup enforcement, bootstrap-password detection, password-strength guidance, in-process rate limiting, local auth audit logging, and privileged-change security audit logging exist. |
| Phase 3: Camera adapters and test shot | Partial | Mock and rpicam/libcamera implemented and validated with an IMX290 on Raspberry Pi. Initial ZWO adapter exists with fake-SDK tests; real ZWO hardware validation is pending. gPhoto2, V4L2, INDI, custom command are placeholders. |
| Phase 4: Capture daemon and realtime | Done | Scheduled daemon loop, shared capture service, persistent job claiming for test/single/scheduled/sequence captures, day/night profile selection, restart-safe per-mode interval and save policy, next-capture due visibility, latest-only day captures, saved night captures, end-of-night product queueing, graceful stop reporting, real-Pi validated rpicam hard-cancel, pause/resume/stop queue semantics, active-window checks and UI preview, lock-file duplicate-loop guard with stale lock recovery, heartbeat/activity reporting, interrupted job recovery, SSE endpoint, Pi reboot service startup acceptance, IMX290 capture after restart/reboot acceptance, and accelerated indoor Pi day/night acceptance exist. Real outdoor overnight field validation remains a hardening task. |
| Phase 5: Image storage/gallery/latest/metadata | Done | Capture artifacts, metadata sidecars, thumbnails, stable latest copies, image rows, gallery, latest image, public latest/product endpoints gated by public-page settings, public sky page, image detail, basic file/image metadata extraction, and JSON-safe EXIF extraction exist. |
| Phase 6: Processing worker/products/retention | Done | Worker claims jobs, thumbnail reprocess exists, keogram JPEG generation, ffmpeg timelapse/mini-timelapse generation, startrail generation, image/product retention cleanup, and product deletion exist, and product job progress is visible in the UI. Remote upload execution is intentionally tracked in Phase 9. |
| Phase 7: Overlay/modules | Done | Trusted built-in overlay module seeding, API configuration, capture-time text rendering with variables, image metadata/flagging, expanded overlay editor, built-in post-capture module flow execution, external module manifest registration/listing/deletion, and Modules UI exist. Custom code upload/execution is intentionally disabled until a future sandbox/signing runtime is designed. |
| Phase 8: Installer/systemd/support/docs | Partial | Scripts and units exist. Shellcheck CI, installer dry-run/idempotency tests, service-control sudoers generation, interactive first-setup prompts, ZWO `libasi`/SDK provisioning hooks, real Pi install, repeat install, service restart, and reboot verification exist. Nginx option and broader Pi camera verification are open. |
| Phase 9: Allsky migration/remote upload | Done | Allsky detection, dry-run count preview, compact unsupported-setting report, worker-backed recognized image/product/dark-frame/overlay-asset import with progress/import-log output, selected observatory/schedule/public/storage/processing/profile settings import, basic overlay text import with rollback restore, camera hint capture, rollback of Sky Weaver-created rows/files/settings/profile changes, Migration UI loading/job polling, and asset-tree exclusion for Allsky HTML/docs/config/overlay files from gallery imports exist. Filesystem, rsync-over-SSH, SCP-over-SSH, SFTP-over-SSH, FTP, and FTPS remote targets, encrypted local target configs, upload queue/retry, worker-backed upload execution, upload job listing/detail views, credential redaction, and Remote Upload UI exist. Full Allsky setting parity and rendering imported overlay image assets remain future polish, not Phase 9 blockers. |
| Phase 10: Polish/mobile/tests/hardening | Partial | Mobile API docs, latest/status/gallery endpoints, route bundle splitting, image detail route, system health diagnostics/service detail UI with failure analysis and unit history, worker heartbeat/activity reporting, private download auth hardening, authenticated admin thumbnails, mobile gallery dialog scroll/close behavior, Deployment operator page, frontend route smoke tests, admin-route auth tests, settings validation tests, schedule calculation tests, destructive image delete policy tests, processing job lifecycle tests, expanded API-key scope-boundary tests for read, write, admin, private-download, and service-control routes, public product archive/compact-layout tests, Remote Upload operator UX polish, initial frontend component tests, and CI workflow exist. Broader tests, UX polish, performance, and security hardening remain. |

## Open Topics

### Highest Priority

- Run real outdoor overnight field validation with the IMX290/rpicam setup once the Pi/camera can be placed outside.
- Keep API-key scope tests updated as new endpoint groups are added.

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
- Validate the ZWO native-SDK backend on real ZWO ASI hardware and expand control coverage.
- Add INDI adapter skeleton with expected integration contract.
- Design custom command adapter with explicit security controls and sandbox warnings.

### Image Pipeline

- Add image resize/crop/stretch processing.
- Add configurable bad image thresholds.
- Add dark-frame capture and median combine.
- Add dark-frame matching by exposure/gain/temperature/camera.
- Add overlay live preview and preset import/export.
- Add star count placeholder or simple implementation.
- Add cloud score placeholder or simple heuristic.

### Night Products

- Expand keogram generation options and UI progress.
- Expand product progress reporting with detailed per-frame/per-stage progress.
- Add regenerate by date/date range.
- Add download-ready UI states.
- Add skip bad/overexposed image rules.

### Web UI

- Add capture control page separate from dashboard.
- Add overlay live preview and preset import/export.
- Design future sandboxed/signed external module runtime.
- Add dark frames page.
- Add remote upload page.
- Expand system health views with deeper unit history, failure classification, and recovery guidance after more real Pi failures are observed.
- Allsky migration page exists with preview loading and job polling; richer historical job browsing remains future UI polish.
- Expand Deployment with optional nginx guidance after that install path exists.
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
- Add CSRF protection if cookie auth is introduced.
- Add better secret handling for remote targets.
- Redact all secrets in diagnostics and logs.
- Add file permission checks for config and database.
- Review all subprocess calls and future custom-command execution for injection risk.
- Keep API-key scope-boundary tests updated when new protected endpoint groups are added.

### Allsky Migration

- Import supports recognized images, timelapses, keograms, startrails, dark frames, overlay assets, selected observatory/schedule/public-page/storage/processing/profile settings, basic overlay text settings, and camera hints.
- Unsupported setting report exists for known Allsky config files and unmapped keys; expand it into richer setting-level translation diagnostics.
- Import log and basic UI progress exist; expand with richer per-file failure details if future partial-import behavior is added.
- Rollback removes Sky Weaver-created rows/files and restores settings/profile snapshots for the migration job.
- Keep original Allsky data untouched.

### Remote Upload

- Filesystem, rsync-over-SSH, SCP-over-SSH, SFTP-over-SSH, FTP, and FTPS remote target config UI exists with summary counters, mobile-friendly action layout, visible loading/error states, guarded target creation, and per-action pending feedback.
- Upload retry queue exists for failed upload jobs.
- Upload job list and detail views expose target metadata, attempts, timing, source, destination, and last error.
- Remote target configs are stored as a local Fernet encrypted envelope derived from `SKYWEAVER_SECRET_KEY`; keep that key stable across upgrades.
- Redact credentials everywhere.

### Plugin/Module System

- Expand built-in module registry.
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
- Keep uploaded custom code disabled until sandboxing/signing is implemented.

### Database and Migrations

- Add backup/restore validation.
- Expand migration fixture tests as future schema changes are introduced.
- Continue adding targeted indexes as new gallery, job, log, event, and product query patterns are added.

### Testing and CI

- Expand component tests for remaining operational pages and edge states.
- Add browser-level smoke coverage for public page enabled/disabled states, public product archives, and compact mobile layout.
- Expand GitHub Actions after Pi validation:
  - installer tests for future interactive setup and nginx paths
  - real migration fixture tests
  - OpenAPI diff checks

## Known Current Limitations

- Capture daemon now performs day/night scheduled captures and consumes queued test-shot, single-capture, and sequence jobs. Restart-safe per-profile interval/save controls, next-capture due visibility, latest-only unsaved captures, end-of-night product queueing, graceful stop fallback, real-Pi validated rpicam hard-cancel, pause/resume/stop queue semantics, daemon activity visibility, Dashboard capture job progress, and interrupted job requeue on service start exist. Real outdoor overnight image quality and environmental stability still need field validation.
- Worker now generates thumbnails, keograms, ffmpeg timelapses, mini timelapses, and startrails. Image/product retention cleanup, product deletion, filesystem upload execution, and Health-visible heartbeat/PID/last-job reporting exist.
- Product endpoints queue jobs; keogram, timelapse, mini timelapse, and startrail currently produce downloadable night products.
- Public page exists for latest-image display with compact responsive metadata and honors the public-page enabled setting; richer public archives and branding controls are still open.
- Phase 7 has a trusted built-in overlay module, module-flow execution, and external manifest registration. Arbitrary custom code execution is intentionally not enabled without sandboxing/signing.
- ZWO ASI support is adapter-backed with native-SDK fake tests, but it has not yet been validated with real ZWO hardware in this environment.
- Remote upload supports filesystem, rsync-over-SSH, SCP-over-SSH, SFTP-over-SSH, FTP, and FTPS targets. SSH-based targets use key/agent auth only. Remote target configs are encrypted locally and API responses redact secret fields.
- Private image/product download routes and private image thumbnails require `read:images`; admin Dashboard/Gallery thumbnails are fetched with the current bearer token. Unauthenticated downloads remain limited to `/api/v1/public/...` routes and remain gated by the public-page setting.
- Allsky migration imports images, dark frames, keograms, startrails, timelapses, overlay assets, selected settings, camera profile settings, basic overlay text settings, and camera hints by copying files into Sky Weaver storage and applying a restorable settings snapshot. Full Allsky setting parity and rendering imported overlay images remain future work.
- API server no longer performs camera capture inline for test shots; test-shot requests enqueue daemon-owned `test` jobs so manual verification still works while automation is stopped.
- Tailwind 4 is enabled through the official Vite plugin while preserving the existing theme config and shadcn animation utilities.
- Lint passes with zero warnings in the current local validation.
- Real Raspberry Pi install, service restart, reboot, and IMX290 real-camera capture acceptance passed on a Raspberry Pi 3 Model B running Debian 13/trixie.

## Recent Verification

Most recent local checks on 2026-07-01:

- `backend\\.venv\\Scripts\\python -m pytest -p no:cacheprovider --basetemp .tmp\\pytest-all backend\\tests`: passed with 95 tests.
- `npm run lint`: passed with zero warnings.
- `npm test`: passed with 22 tests.
- `npm run build`: passed.
- `git diff --check`: passed for the current Phase 10 public product archive/mobile compact coverage changes.
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
- `/home/pi/sky-weaver-hub` fast-forwarded to `1d31045` and `sudo ./upgrade.sh` passed with backup `/var/lib/skyweaver/backups/20260624-193839`.
- Real rpicam hard-cancel acceptance passed with IMX290: a queued 60s single capture reached `running`, `/api/v1/capture/stop` marked one in-progress job for best-effort cancel, final job `76f714a2-c0db-459c-a6df-9a3dd7d81a84` ended `canceled` with `stop_mode: hard_cancel`, adapter method `terminate`, and no leftover `rpicam-still`/`libcamera-still` process.
- `/home/pi/sky-weaver-hub` fast-forwarded to `f3de529` and `sudo ./upgrade.sh` passed with backup `/var/lib/skyweaver/backups/20260624-195331`.
- Real Pi auth-audit acceptance passed: five failed local login attempts returned `401`, the sixth returned `429`, `/api/v1/logs?source=auth` showed `Login failed` plus `Login blocked by rate limit` entries with failure count/client context, and the submitted test password was absent from log JSON.

Raspberry Pi accelerated Phase 4 acceptance on 2026-06-29:

- `/home/pi/sky-weaver-hub` was already at `45badde`; `sudo ./upgrade.sh` completed with backup `/var/lib/skyweaver/backups/20260629-133322`.
- `skyweaver.target`, `skyweaver-api.service`, `skyweaver-capture.service`, and `skyweaver-worker.service` were active; `systemctl --failed` reported no failed units; `/api/v1/health` returned `ok`.
- Simulated night mode used a fixed active window and short interval with the IMX290/rpicam primary camera. Saved `scheduled` night captures completed, including jobs `62a2578d-790c-47c4-b885-d2d9d8d6b4a1` and `6582ddcf-6c55-407a-bdc3-5a1ed295da9a`.
- Restart-safe interval acceptance passed: `skyweaver-capture.service` was restarted after a scheduled night capture, no duplicate scheduled capture appeared during the immediate post-restart wait, and the next scheduled capture completed after the interval became due.
- Simulated day mode used a fixed inactive night window with daytime `save_enabled=false`; scheduled day captures updated latest artifacts with `unsaved_latest=true` without growing the saved gallery count.
- End-of-night product queueing passed for day key `20260629`: keogram job `af7bcd25-1f1d-48d4-81b4-da83e400ddb1` and startrail job `0752e569-3f97-48c1-a49a-022435a9c5a9` were queued once from the night-to-day transition and completed.
- Queue/control acceptance passed through the API: daemon-owned test shot job `a86653cb-3a8e-4804-8f65-ac5d150c3d1f`, pause/resume single job `5550a1a8-0955-4834-8b0b-0b259519efcf`, sequence job `76bf02b6-2aaf-41da-af12-0e7727b7473a` with 2/2 frames, and stop-canceled pending job `2bb03ae3-f340-47fd-8163-21c82baffca8` all behaved as expected.
- After acceptance, the saved schedule/profile settings were restored. Final state showed capture running, no failed units, all Sky Weaver services active, `last_error=NULL`, and capture daemon heartbeat age `0` seconds.

## Recommended Next Phase

The next development phase should focus on Phase 8/10 operational hardening and observability, because capture, products, public latest, overlays/modules, and local service management now have working implementation paths.

Suggested next tasks:

1. Run real outdoor overnight field validation once the Pi/camera can be placed outside.
2. Add browser smoke coverage for migration and remote-upload forms with real API fixtures.
3. Add optional nginx reverse proxy and broader installer smoke coverage for fresh Pi OS Bookworm images.
4. Add cursor pagination and richer filters for mobile clients.
