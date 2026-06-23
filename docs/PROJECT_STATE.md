# Sky Weaver Hub Project State

Last updated: 2026-06-23

This document tracks the current implementation state against the all-sky platform prompt. It is intended to be updated after each implementation phase.

## Current Summary

Sky Weaver Hub has moved from a mock dashboard toward a local-first Raspberry Pi/Linux all-sky platform. The repository now has a FastAPI backend, SQLite persistence, a camera adapter interface, mock capture with real image artifacts, an initial Raspberry Pi camera adapter, a daemon-owned scheduled capture loop, API-key authentication, systemd and installer scaffolding, and a React UI wired to the local API.

The product is not yet Allsky feature-complete. The main missing areas are sun-angle scheduling, full capture pause/resume semantics, full image-product generation, public sky page, overlay/module workflows, remote upload execution, complete Allsky import, and Raspberry Pi acceptance testing.

## Repo Map

| Area | Current State |
| --- | --- |
| Frontend | Vite, React 19, TypeScript, shadcn/Radix UI, Tailwind 3.4.19 pinned to preserve the original design system. |
| Backend | FastAPI under `backend/skyweaver`, OpenAPI docs at `/api/docs`, REST API under `/api/v1`. |
| Database | SQLite via stdlib `sqlite3`, schema seeded in `backend/skyweaver/db.py`. No external database dependency. |
| Storage | Local filesystem storage for images, thumbnails, products, logs, and config. Dev defaults are local paths; system install targets `/var/lib/skyweaver`, `/etc/skyweaver`, `/var/log/skyweaver`. |
| Auth | Local admin JWT login plus hashed API keys with scopes. Bootstrap admin still needs first-setup hardening. |
| Camera abstraction | `CameraAdapter` base class plus working `mock` adapter and initial `rpicam`/`libcamera` adapter. Other adapters are placeholders with actionable errors. |
| UI/API integration | Dashboard, Cameras, Schedule, Gallery, Night Products, Logs, Settings, API Keys, and Developer API call the local backend. |
| Deployment | `install.sh`, `upgrade.sh`, `uninstall.sh`, `support.sh`, and systemd units exist. Installer is not yet fully interactive. |
| Tests | Backend pytest coverage for health/status, login, API keys, mock capture, scheduled daemon capture, queued single-capture execution, migration preview, and mock adapter. Frontend smoke test exists. |

## Implemented Capabilities

### Backend/API

- `/api/v1/health`
- `/api/v1/status`
- `/api/v1/system/metrics`
- `/api/v1/system/services`
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
- A daemon lock file prevents duplicate daemon loops from running in the same data directory.
- Manual/test-shot API captures, queued single captures, and scheduled daemon captures now share the same capture execution path.
- `/api/v1/capture/single` creates a persistent pending capture job for daemon execution.
- Backend tests verify daemon-run scheduled capture creation, interval gating, and queued single-capture completion.

### Frontend

- Local login page.
- Dashboard with latest image, capture controls, status, metrics, and recent captures.
- Cameras page with detection, adapter selection, night-profile editing, and test shot.
- Schedule page with sun-angle/fixed/manual mode settings.
- Gallery page with day/mode/quality filters and image detail.
- Night Products page queues product jobs.
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
- Upgrade script backs up config/database and rebuilds.
- Uninstall script removes services and optionally data.
- Support script collects OS, camera, service, journal, disk, config-redacted, and API health details.

### Documentation

- README updated with architecture, quickstart, API examples, status, and limitations.
- Dedicated docs exist for install, upgrade, uninstall, Raspberry Pi, cameras, API, mobile API, Allsky migration, plugin development, security, and troubleshooting.

## Phase Status

| Phase | Status | Notes |
| --- | --- | --- |
| Phase 0: Repo inspection | Done | React/Vite Lovable-style frontend identified; Supabase flow replaced by local API direction. |
| Phase 1: API skeleton and SQLite | Mostly done | Backend, schema, health/status, API client, core routes, and mock capture exist. Dedicated migration framework still needed. |
| Phase 2: Auth/API keys/settings/docs | Mostly done | JWT login, API-key scopes, settings, API Keys UI, and Developer API UI exist. First-run setup and rate limiting are still open. |
| Phase 3: Camera adapters and test shot | Partial | Mock and rpicam/libcamera implemented. ZWO, gPhoto2, V4L2, INDI, custom command are placeholders. |
| Phase 4: Capture daemon and realtime | Partial | Scheduled daemon loop, shared capture service, persistent job claiming for single/scheduled captures, interval gating, lock-file duplicate-loop guard, and SSE endpoint exist. Sun-angle scheduling, sequence queue handling, pause semantics, and reboot-safe heartbeat/state are open. |
| Phase 5: Image storage/gallery/latest/metadata | Partial | Mock capture artifacts, metadata, thumbnails, image rows, gallery, latest image exist. Latest symlink/copy and broader metadata extraction are open. |
| Phase 6: Processing worker/products/retention | Early scaffold | Job endpoints and worker stub exist. Timelapse, keogram, startrail, mini timelapse, cleanup, and upload execution are open. |
| Phase 7: Overlay/modules | Early scaffold | Module tables/endpoints exist. Overlay editor, processor, built-in modules, safe module execution are open. |
| Phase 8: Installer/systemd/support/docs | Partial | Scripts and units exist. Interactive setup, nginx option, shellcheck, idempotency tests, and Pi verification are open. |
| Phase 9: Allsky migration/remote upload | Early scaffold | Detection and dry-run count preview exist. Real import, rollback, unsupported-setting report, and remote upload execution are open. |
| Phase 10: Polish/mobile/tests/hardening | Partial | Mobile API docs and latest/status/gallery endpoints exist. CI, broader tests, UX polish, performance, and security hardening remain. |

## Open Topics

### Highest Priority

- Expand the capture daemon into complete queue ownership:
  - move all remaining long-running capture execution out of direct API request path
  - persist queued commands and daemon heartbeat
  - distinguish running, paused, stopped, and failed state precisely
  - survive reboot
  - gracefully stop after current exposure
- Implement schedule calculation using latitude, longitude, timezone, sun angle, and manual overrides.
- Complete mock acceptance flow end to end:
  - start capture
  - images continuously appear
  - latest image updates
  - gallery updates
  - reboot/service restart behavior works
- Add first-run setup flow:
  - force admin password change
  - observatory location
  - timezone
  - primary camera adapter
  - public page enabled/disabled

### Raspberry Pi Deployment

- Test `install.sh` on fresh Raspberry Pi OS Bookworm 64-bit.
- Add interactive setup questions required by the prompt.
- Add explicit Raspberry Pi model and Bookworm detection messages.
- Add camera presence check during install.
- Add optional nginx reverse proxy.
- Add `skyweaver` convenience command or documented aliases for start/stop/restart/status.
- Add shellcheck coverage.
- Add installer dry-run/idempotency tests.
- Confirm service permissions and ownership on real Pi.

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

- Implement timelapse generation via ffmpeg.
- Implement mini timelapse generation.
- Implement keogram generation.
- Implement startrail generation.
- Add product progress reporting.
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
- Add system health page with service controls, package versions, diagnostics export.
- Add Allsky migration page.
- Add deployment/installer docs page.
- Improve mobile layouts after real data flows are in place.
- Consider bundle splitting; current build warns that the main JS chunk is over 500 kB.

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
- Add OpenAPI artifact generation in CI.
- Add websocket endpoint if SSE is insufficient.
- Ensure public endpoints are explicitly unauthenticated and admin endpoints are protected.

### Security

- Remove any permanent reliance on bootstrap `admin / skyweaver-change-me`.
- Add first-setup-required enforcement.
- Add auth endpoint rate limiting.
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
- Add component tests for Dashboard, Settings, Gallery, API Keys.
- Add public page no-auth test once implemented.
- Add admin route auth tests.
- Add backend tests for:
  - schedule calculation
  - settings validation
  - image database CRUD
  - processing job lifecycle
  - every API-key scope boundary
- Add shellcheck.
- Add GitHub Actions workflow:
  - frontend lint
  - frontend build
  - frontend tests
  - backend tests
  - shellcheck
  - OpenAPI generation artifact

## Known Current Limitations

- Capture daemon now performs scheduled captures and consumes queued single-capture jobs, but it does not yet have a heartbeat, sequence handling, or full pause/resume semantics.
- Worker is still a service stub, not a full processing loop.
- Product endpoints currently queue jobs but do not generate real files.
- Public page is not implemented.
- Remote upload is not implemented.
- Allsky migration does not yet import data.
- API server currently still performs test-shot capture inline through the shared service for UX; other long capture paths should continue moving toward daemon/queue ownership.
- Tailwind is intentionally pinned to 3.4.19 to preserve the original design. Tailwind 4 requires a separate design-system migration.
- Lint passes with warnings from existing generated UI/hook patterns.
- Real Raspberry Pi hardware acceptance has not been run in this environment.

## Recent Verification

Most recent checks run during implementation:

- `npm run build`: passed
- `npm test`: passed
- `npm run lint`: passed with warnings only
- `npm audit --audit-level=high`: passed with 0 vulnerabilities
- `backend\\.venv\\Scripts\\python -m pytest backend\\tests`: passed with 8 tests

## Recommended Next Phase

The next development phase should focus on real schedule calculation and daemon service visibility, because queued single captures and scheduled captures now share daemon execution.

Suggested next tasks:

1. Implement sun-angle schedule calculation and next-transition preview.
2. Add a database heartbeat in addition to the lock file for better service visibility.
3. Make `start`, `stop`, `pause`, and `resume` control daemon behavior with explicit state transitions.
4. Add queued sequence capture support.
5. Run a mock-camera overnight simulation that creates multiple captures and verifies latest/gallery updates.
