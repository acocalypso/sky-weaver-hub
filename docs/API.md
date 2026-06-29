# API

OpenAPI docs are served at `/api/docs`.

All stable endpoints live under `/api/v1`. Success responses use:

```json
{ "data": {}, "meta": { "request_id": "...", "timestamp": "..." } }
```

Errors use:

```json
{ "error": { "code": "HTTP_ERROR", "message": "...", "details": {}, "request_id": "..." } }
```

External clients use `Authorization: Bearer <API_KEY>`. Admin UI login receives a bearer token from `/api/v1/auth/login`.

`GET /api/v1/logs?source=auth` exposes local auth audit entries to authenticated status readers, including failed login/setup attempts, rate-limit blocks, and successful login after previous failures. `GET /api/v1/logs?source=security` exposes privileged-change audit entries for setup completion, password changes, user/API-key lifecycle, settings, schedule, camera, and camera-profile changes. Audit contexts include actor/client metadata, target identifiers, scopes, and changed field names, but not submitted passwords, raw API keys, key hashes, or secret setting values.

Capture requests that can touch hardware are queued. `/api/v1/capture/test-shot`, `/api/v1/capture/single`, and `/api/v1/capture/sequence` return a capture job immediately; clients should poll `/api/v1/capture/jobs` or `/api/v1/capture/jobs/{job_id}` and then read `/api/v1/images/latest` or image detail endpoints after completion.

Scheduled capture uses the primary camera's `daytime` or `nighttime` profile based on the configured schedule window. Profile settings now include `capture_enabled`, `save_enabled`, and `interval_seconds`; `save_enabled=false` updates the stable latest public artifacts without inserting a permanent gallery image row. The daemon gates scheduled captures from persisted completed `scheduled` jobs, so restarting the capture service does not forget the interval. `POST /api/v1/schedule/preview-tonight` also returns `capture_mode`, `capture_enabled`, `save_enabled`, `interval_seconds`, `last_scheduled_capture_at`, `next_capture_due_at`, `capture_due`, and `seconds_until_due` for operator and mobile-client schedule displays. Night profiles can also enable `end_of_night_keogram`, `end_of_night_startrail`, `end_of_night_timelapse`, and `end_of_night_mini_timelapse` so the daemon queues processing jobs once when the night window ends.

Successful captures also publish stable latest artifacts under the local data directory:

- `latest/latest.<format>`
- `latest/latest-thumbnail.<format>` when thumbnail generation succeeds
- `latest/latest.json`

Image row `metadata` includes capture context, environment readings, analysis values, adapter metadata, and `storage` metadata. `metadata.storage` contains JSON-safe file details, image format/mode/dimensions, and readable EXIF tags when the source image provides them. Large binary EXIF values such as maker notes are not stored.

Image and product cleanup endpoints use the same success envelope and require `write:processing`. `DELETE /api/v1/images/{image_id}` removes the database row plus the owned image file, thumbnail, JSON sidecar, and matching latest artifacts; if an older image remains it republishes that image as latest. `POST /api/v1/images/retention/run?days=30` removes image rows and owned artifacts older than the cutoff. Generated night products have matching lifecycle endpoints: `DELETE /api/v1/products/{product_id}` removes the product row and owned product/thumbnail files, and `POST /api/v1/products/retention/run?days=30` removes old generated products.

Public latest endpoints are intentionally unauthenticated for kiosk/public-page/mobile display use when `public_page.enabled` is true. When the public page is disabled, these endpoints return `403` with `Public page is disabled`:

- `GET /api/v1/public/latest`
- `GET /api/v1/public/latest/download`
- `GET /api/v1/public/latest/thumbnail`

`GET /api/v1/system/services/{name}` returns per-service `systemctl show` properties, recent `journalctl` output, a `failure_analysis` summary, and `unit_history` timestamps/restart metadata when systemd tooling is available. These fields are read-only diagnostics for operators and mobile clients; service actions remain separate admin-scoped `POST /api/v1/system/services/{name}/{action}` calls.

`POST /api/v1/capture/stop` cancels pending/claimed capture jobs immediately and reports any already-running exposure in `in_progress_jobs`/`in_progress_job_ids`. It also records best-effort cancel intent in `cancel_requested_jobs`/`cancel_requested_job_ids`; adapters with safe hard-cancel support, currently the rpicam/libcamera adapter, may interrupt the exposure in the capture daemon process and mark the job `canceled` with `stop_mode: hard_cancel`. Unsupported adapters finish gracefully and are marked `stopped` with `completed_after_stop` and `stop_mode: graceful`.
