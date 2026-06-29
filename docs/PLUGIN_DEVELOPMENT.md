# Plugin Development

Sky Weaver uses a safer Allsky-inspired module system. Built-in modules are trusted. Uploaded custom modules are disabled until sandboxing and signing are implemented and should be treated as local code execution.

## Built-In Overlay Module

`builtin.overlay` is seeded as a trusted built-in module and is disabled by default. When enabled, it renders configured text lines onto each captured image before metadata sidecars, thumbnails, and latest artifacts are generated.

Supported template variables:

- `{observatory_name}`
- `{captured_at}`
- `{date}`
- `{time}`
- `{mode}`
- `{camera_id}`
- `{camera_model}`
- `{exposure_ms}`
- `{gain}`
- `{temperature_c}`

Admins can configure the built-in overlay through `/modules` or `PATCH /api/v1/modules/builtin.overlay`. Uploaded custom module execution remains disabled.

Planned triggers:

- `daytime_capture`
- `nighttime_capture`
- `day_to_night_transition`
- `night_to_day_transition`
- `periodic`
- `manual`
