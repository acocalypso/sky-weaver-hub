# Plugin Development

Sky Weaver uses a safer Allsky-inspired module system. Built-in modules are trusted and can run inside first-party flows. External modules can be registered from a manifest so they are visible to admins and future tooling, but they are forced disabled and untrusted. Uploaded custom code execution remains disabled and should be treated as local code execution until a future security phase adds a sandboxed runtime.

## Module Manifest Contract

Register an external module manifest with `POST /api/v1/modules/register`:

```json
{
  "id": "external.example-overlay",
  "name": "Example overlay",
  "description": "Manifest-only module package.",
  "version": "0.1.0",
  "author": "Example",
  "capabilities": ["post_capture"],
  "settings_schema": { "type": "object" },
  "settings": {}
}
```

Rules:

- `id` must be lowercase letters, numbers, dots, underscores, or dashes.
- External modules cannot use the `builtin.` namespace.
- Registered external modules are stored as disabled and untrusted.
- External modules cannot be enabled, inserted into module flows, or executed until sandboxing/signing exists.
- `POST /api/v1/modules/upload` remains disabled for code archives.

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

Admins can configure the built-in overlay through `/modules` or `PATCH /api/v1/modules/builtin.overlay`. The built-in `post_capture` flow controls whether this overlay participates in capture-time processing.

Current trigger:

- `post_capture`

Future trigger candidates:

- `daytime_capture`
- `nighttime_capture`
- `day_to_night_transition`
- `night_to_day_transition`
- `periodic`
- `manual`
