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

Capture requests that can touch hardware are queued. `/api/v1/capture/test-shot`, `/api/v1/capture/single`, and `/api/v1/capture/sequence` return a capture job immediately; clients should poll `/api/v1/capture/jobs` or `/api/v1/capture/jobs/{job_id}` and then read `/api/v1/images/latest` or image detail endpoints after completion.

Successful captures also publish stable latest artifacts under the local data directory:

- `latest/latest.<format>`
- `latest/latest-thumbnail.<format>` when thumbnail generation succeeds
- `latest/latest.json`

Public latest endpoints are intentionally unauthenticated for kiosk/public-page/mobile display use when `public_page.enabled` is true. When the public page is disabled, these endpoints return `403` with `Public page is disabled`:

- `GET /api/v1/public/latest`
- `GET /api/v1/public/latest/download`
- `GET /api/v1/public/latest/thumbnail`

`GET /api/v1/system/services/{name}` returns per-service `systemctl show` properties, recent `journalctl` output, a `failure_analysis` summary, and `unit_history` timestamps/restart metadata when systemd tooling is available. These fields are read-only diagnostics for operators and mobile clients; service actions remain separate admin-scoped `POST /api/v1/system/services/{name}/{action}` calls.

`POST /api/v1/capture/stop` cancels pending/claimed capture jobs immediately and reports any already-running exposure in `in_progress_jobs`/`in_progress_job_ids`. It also records best-effort cancel intent in `cancel_requested_jobs`/`cancel_requested_job_ids`; adapters with safe hard-cancel support, currently the rpicam/libcamera adapter, may interrupt the exposure in the capture daemon process and mark the job `canceled` with `stop_mode: hard_cancel`. Unsupported adapters finish gracefully and are marked `stopped` with `completed_after_stop` and `stop_mode: graceful`.
