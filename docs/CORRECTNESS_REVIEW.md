# Correctness Review

Reviewed: 2026-10-16. This is a targeted bug-fix pass over source baseline `1db48f4`, preserving the documentation and dependency refresh. It is not a claim that every defect or hardware failure mode has been eliminated.

## Backend fixes

- **User permissions:** login previously assigned admin scope to every user. Permissions now follow the stored admin/operator/viewer role on each request. Demoting or deleting an account therefore affects existing tokens. Missing JWT subject/expiry claims are rejected as unauthorized rather than falling through to missing-key errors or permissive defaults.
- **API-key lifetime:** stored expiration was ignored. Expiration is now validated with an explicit timezone and enforced before updating usage; malformed legacy values fail authentication. API keys cannot make current-user password changes.
- **Password prefix matching:** verification previously truncated inputs longer than bcrypt's 72-byte limit, accepting arbitrary suffixes after a valid 72-byte password. Overlong input is now rejected, including multibyte UTF-8 input.
- **Daemon startup:** interrupted capture jobs were recovered before acquiring the daemon lock, allowing a rejected second daemon to reset work still owned by the first. Recovery now runs only after lock acquisition.
- **Event delivery:** SSE used `id > last_id` even though IDs are random UUIDs. Batches now use insertion order, expose UUID resume IDs, and honor `Last-Event-ID`. Clock rollback and reverse UUID ordering do not skip events. Public data fields stay intact; the internal cursor is not exposed.

No schema migration or dependency was needed for these fixes. The existing local SQLite event table supplies the internal insertion cursor. Event retention/vacuum maintenance must preserve cursor semantics if added later.

## Frontend fixes

- **Session races:** pending restoration/login requests could restore a signed-out user or clear a newer session when an older request failed. Request generations now invalidate stale results and unmounted requests; failures clear incomplete credentials and finish loading.
- **Setup verification:** admin routes no longer assume setup is complete when the API lookup fails. They show a retry action. Non-admin sessions do not call an admin-only setup endpoint.
- **Calendar adapter:** migrated removed DayPicker v8 class/component names to the installed v10 API, including day buttons and directional chevrons.
- **Resizable adapter:** replaced removed `PanelGroup`/`PanelResizeHandle` exports with `Group`/`Separator`, preserving the wrapper's `direction` alias and correcting separator orientation selectors.
- **Chart adapter:** updated tooltip/legend types, handled absent raw payload data and zero values, and passed the full entry array to the formatter's fifth argument rather than one entry's raw data.
- **Type contracts:** removed incompatible native/custom input handler intersections, corrected the dashboard saved/public image union, and declared ES2021 library support for existing `replaceAll` calls. `npm run typecheck` now checks the app and Vite config; all 36 baseline diagnostics are resolved.

## Regression coverage

New backend cases cover role boundaries, existing-session demotion/deletion, required JWT claims, expiry validation/usage accounting, password prefix matching, API-key password restrictions, rejected-daemon startup and SSE batches/resume frames.

New frontend cases cover out-of-order login/restoration/sign-out responses, failed principal lookup, unmount, setup failure/retry and viewer access, calendar selection/navigation, both panel orientations, tooltip zero/missing payload data, formatter arguments and legend labels.

The final verification results are recorded in [Project State](PROJECT_STATE.md). The dependency/runtime recheck is documented in [Dependency Maintenance](DEPENDENCIES.md). Hardware capture, outdoor overnight behavior, server-side logout/password-change token revocation, automatic retention/publication and observing-night product windows remain outside this fix pass.

Final local checks: **142 backend tests passed, 1 skipped on each of Python 3.12.10 and 3.15.0**; **41 frontend tests passed**; **11 browser smoke tests passed, 1 intentional skip**; lint, application/config type checks, production build, dependency checks and OpenAPI generation passed. npm audit reports zero vulnerabilities. No dependency-major compatibility waiver was needed; TypeScript remains at the latest version supported by the lint tooling. CI now enforces `npm run typecheck` as well as lint/build/tests.
