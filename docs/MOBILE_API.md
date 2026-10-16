# Mobile API

Mobile clients should use:

- `GET /api/v1/status`
- `GET /api/v1/images/latest`
- `GET /api/v1/public/latest`
- `GET /api/v1/public/latest/download`
- `GET /api/v1/public/products`
- `GET /api/v1/images/page?limit=50`
- `GET /api/v1/logs/page?limit=100`
- `GET /api/v1/system/time`
- `GET /api/v1/system/wifi/status`
- `POST /api/v1/capture/start`
- `POST /api/v1/capture/stop`
- `GET /api/v1/events/stream`

Use API keys with least-privilege scopes. CORS is local-only by default and configurable in settings/environment.

SSE frames now include the event UUID in an `id` field. Preserve that value and send `Last-Event-ID` on reconnect to resume after it. Unknown/removed IDs return `400`; reconnect without the header only when replaying retained history is appropriate. Events are delivered in insertion order, including when UUIDs sort backwards or the Pi clock changes. See [API](API.md) for role permissions and API-key expiration rules.

`/api/v1/public/latest`, `/api/v1/public/products`, and their download endpoints are unauthenticated by design when `public_page.enabled` is true. They return only public display metadata, stable latest image bytes, and completed product links within the configured `public_page.product_days` window. When the public page is disabled, mobile clients should treat `403 Public page is disabled` as a user-configured disabled state rather than an authentication failure.

For authenticated gallery browsing, prefer `/api/v1/images/page` over the legacy offset endpoint. It preserves the standard success envelope and returns `items`, `next_cursor`, `has_more`, `limit`, and the applied `filters`. Pass the opaque `next_cursor` value back as `cursor` to load the next page. Supported filters are `day_key`, `mode`, `camera_id`, `bad_image`, `captured_from`, and `captured_to`. Date range filters must be timezone-aware ISO datetimes, for example `2026-07-01T00:00:00Z`.

For authenticated operator logs, prefer `/api/v1/logs/page` over the legacy list endpoint. It uses the same `items`, `next_cursor`, `has_more`, `limit`, and `filters` shape and supports `level` and `source` filters.

Admin-capable mobile clients can use `POST /api/v1/system/time/sync` to set Pi time from the device clock and `POST /api/v1/system/wifi/scan` plus `POST /api/v1/system/wifi/connect` to switch Wi-Fi networks. These routes require the `admin` scope and are intended for local operator setup flows.
