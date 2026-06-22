# AllSky Control Hub — Build Plan

A full-stack web app for controlling an all-sky camera on Linux/Raspberry Pi, with an API-first architecture so external apps can integrate. Built on Lovable Cloud (managed Postgres + Auth + Edge Functions).

## Scope note

This spec is very large (10 feature areas, 28 REST endpoints, 11 DB tables, realtime events, multi-page docs). To keep quality high and credits sane, I'll build it in **3 phases** and confirm at each gate. If you'd rather get a thinner version of everything in one shot, tell me and I'll collapse the phases.

## Architecture

- **Frontend**: React + Vite + Tailwind + shadcn, dark observatory theme (deep navy/indigo background, subtle starfield, cyan/amber accents, monospace for telemetry).
- **Backend**: Lovable Cloud (Supabase under the hood) — Postgres tables, RLS, Auth (email+password), Edge Functions for the public REST API, Realtime channel for events.
- **Hardware abstraction**: a `CameraAdapter` interface in an edge function with a `MockAdapter` implementation. Real adapters (libcamera, gphoto2, INDI, ZWO, webcam, custom) are stubbed with clearly-marked TODOs.
- **API auth**: `Authorization: Bearer <API_KEY>` validated in each edge function against the `api_keys` table (hashed key, scopes, last_used_at).

## Data model (Postgres, all in `public`, RLS on)

- `profiles` (user_id, display_name, role)  — role via separate `user_roles` table + `has_role()` SECURITY DEFINER (per platform rules)
- `user_roles` (user_id, role enum: admin, operator, viewer)
- `api_keys` (id, user_id, name, key_hash, key_prefix, scopes[], last_used_at, revoked_at)
- `cameras` (id, name, model, adapter_type, connection_config jsonb, status)
- `camera_settings` (camera_id, exposure_us, gain, white_balance, binning, resolution, file_format, extras jsonb)
- `capture_jobs` (id, camera_id, type [test|scheduled|manual], state, started_at, ended_at, error)
- `capture_schedule` (id, camera_id, start_condition, end_condition, interval_seconds, ramping jsonb, weather_safe)
- `images` (id, camera_id, captured_at, storage_path, thumb_path, metadata jsonb, tags[], star_count, cloud_score, processing_status)
- `timelapse_jobs` (id, date_range, state, output_path, fps, codec, progress)
- `system_settings` (singleton row: location, timezone, observatory_name, storage paths, retention, defaults)
- `logs` (id, ts, level, source, message, context jsonb)
- `realtime_events` (id, type, payload jsonb, ts) — also broadcast via Supabase Realtime

Storage bucket `allsky-images` (private) for image + thumbnail files; demo seed images included.

## Phase 1 — Foundation (this turn if you approve)

1. Enable Lovable Cloud.
2. Design system: dark observatory theme in `index.css` + `tailwind.config.ts` (semantic tokens, starfield background, status-badge variants, telemetry-card variant).
3. Auth: email/password login + signup, protected app shell, sidebar nav.
4. DB migration: all 11 tables + RLS + grants + `has_role()` + seed demo data (1 camera, ~20 demo images, default settings, sample logs).
5. App shell with routes wired (stubs OK): Dashboard, Cameras, Schedule, Gallery, Timelapses, Logs, Settings, API Keys, Developer API, Deployment.
6. Dashboard page fully built: live latest image, status cards, system health (mocked metrics), tonight timeline (computed from lat/lng via SunCalc), recent gallery, quick actions.

## Phase 2 — Capture, Gallery, Automation

1. Cameras page: list/create/edit, adapter type selector, settings form with validation (zod).
2. Manual capture form + test shot (calls edge function → mock adapter → inserts an `images` row + `capture_jobs` row + broadcasts realtime event).
3. Schedule editor with sun-altitude/twilight conditions, interval, ramping.
4. Gallery: date picker, filters, detail page with metadata + "API response preview" JSON view.
5. Timelapses: create job, queue UI, mock progress.
6. Logs page with filters; Settings page (location, storage, retention, etc.).
7. Realtime: subscribe to `realtime_events` channel; toast + live updates on dashboard.

## Phase 3 — API surface + Docs + Deployment

1. Edge functions implementing all 28 REST endpoints under `/api/v1/*` (one function per resource group: `status`, `cameras`, `capture`, `schedule`, `images`, `timelapses`, `logs`, `settings`, `api-keys`). Bearer-key auth middleware with scope checks. Zod validation. Consistent error envelope `{ error: { code, message, details } }`.
2. API Keys page: create (show key once), list, revoke, scopes selector.
3. Developer API page: base URL, auth, full endpoint reference, curl/JS/Python examples, SSE/Realtime example, scopes table, versioning note.
4. Interactive API docs: a lightweight in-app explorer (endpoint list → method/path/params/example response, "Try it" button using the logged-in user's session).
5. Deployment page: Raspberry Pi OS setup, package list (libcamera, gphoto2, ffmpeg, imagemagick), example systemd unit, env vars, Nginx + HTTPS notes, adapter wiring guide with code pointers.

## Technical details

- Realtime: use Supabase Realtime postgres_changes on `realtime_events` table; an edge function helper `emitEvent(type, payload)` inserts rows.
- Sun timeline: `suncalc` npm package, computed client-side from `system_settings.latitude/longitude`.
- API key hashing: SHA-256 with random 32-byte key; store `key_prefix` (first 8 chars) for UI display, `key_hash` for lookup.
- Role enforcement: dashboard requires login; admin-only routes (Settings, API Keys, Cameras CRUD) gated by `has_role(auth.uid(),'admin')`.
- Mock metrics: deterministic-ish sine-based CPU/mem/temp values from an edge function so charts look alive without real hardware.
- Adapter interface file (`supabase/functions/_shared/camera-adapter.ts`) with `MockAdapter` + commented stubs for libcamera/gphoto2/INDI/ZWO/webcam/custom.

## Open questions (assumptions if you don't answer)

1. **Auth providers?** Assume **email/password only** (no Google) unless you say otherwise.
2. **First admin user?** Assume the first signup is auto-promoted to `admin`.
3. **Demo images?** Assume I generate ~3 starry-sky placeholder images and reuse them as seed data (no per-row generation).
4. **All-in-one vs phased?** Assume phased — I'll stop after Phase 1 and wait for "go" before Phase 2/3. Say "build it all" if you want one mega-turn instead.

Reply **"go"** to start Phase 1, or send changes / answers to the questions above.