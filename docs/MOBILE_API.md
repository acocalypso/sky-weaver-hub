# Mobile API

Mobile clients should use:

- `GET /api/v1/status`
- `GET /api/v1/images/latest`
- `GET /api/v1/public/latest`
- `GET /api/v1/public/latest/download`
- `GET /api/v1/public/products`
- `GET /api/v1/images/page?limit=50`
- `POST /api/v1/capture/start`
- `POST /api/v1/capture/stop`
- `GET /api/v1/events/stream`

Use API keys with least-privilege scopes. CORS is local-only by default and configurable in settings/environment.

`/api/v1/public/latest`, `/api/v1/public/products`, and their download endpoints are unauthenticated by design when `public_page.enabled` is true. They return only public display metadata, stable latest image bytes, and completed product links within the configured `public_page.product_days` window. When the public page is disabled, mobile clients should treat `403 Public page is disabled` as a user-configured disabled state rather than an authentication failure.

For authenticated gallery browsing, prefer `/api/v1/images/page` over the legacy offset endpoint. It preserves the standard success envelope and returns `items`, `next_cursor`, `has_more`, `limit`, and the applied `filters`. Pass the opaque `next_cursor` value back as `cursor` to load the next page. Supported filters are `day_key`, `mode`, `camera_id`, and `bad_image`.
