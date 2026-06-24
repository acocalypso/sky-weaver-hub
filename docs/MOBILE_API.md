# Mobile API

Mobile clients should use:

- `GET /api/v1/status`
- `GET /api/v1/images/latest`
- `GET /api/v1/public/latest`
- `GET /api/v1/public/latest/download`
- `GET /api/v1/images?limit=50&offset=0`
- `POST /api/v1/capture/start`
- `POST /api/v1/capture/stop`
- `GET /api/v1/events/stream`

Use API keys with least-privilege scopes. CORS is local-only by default and configurable in settings/environment.

`/api/v1/public/latest` and its download endpoints are unauthenticated by design and return only public display metadata plus stable latest image bytes.
