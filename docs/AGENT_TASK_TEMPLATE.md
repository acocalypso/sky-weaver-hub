# Sky Weaver Hub Agent Task Template

Use this template when assigning implementation work to Codex or a multi-agent coding team. It is designed to move work from casual prompting into agentic engineering: clear intent, bounded context, scoped execution, validation, and reviewable evidence.

For dependency-specific work, the agent must report whether Context7 MCP was used and note any important documentation source, package version, or assumption that affected the implementation.

````text
# Task For GPT-5.5 Codex Multi-Agent Team

Repository:
C:\Users\Aco\Desktop\Dev-Tools\sky-weaver-hub

Task title:
<short imperative title>

Task:
<describe the concrete implementation task in 1-4 paragraphs>

Why this matters:
<explain the product/user outcome, operational problem, or bug being fixed>

Operating mode:
<Conductor | Orchestrator | Background/Delegated>

Use Conductor for ambiguous, risky, architectural, hardware-facing, installer/systemd, auth, migration, or production-sensitive work.
Use Orchestrator for well-specified multi-file work with clear tests and existing patterns.
Use Background/Delegated only for narrow, reproducible tasks with explicit acceptance criteria and validation.

Current project context:
- Sky Weaver Hub is Raspberry Pi/Linux first and local-first.
- The Web UI is Vite/React and talks to the local FastAPI `/api/v1` backend.
- The backend uses FastAPI, SQLite storage, API-key-ready auth, and stable response envelopes.
- The capture daemon owns scheduled and queued capture work.
- Camera support must stay behind adapter interfaces.
- Installer/systemd scripts are part of the production surface.
- Allsky migration currently supports detection and dry-run preview; real import/rollback may still be scaffolded unless this task explicitly changes that.

Context packet:
- User request: <paste the user request or issue text>
- Relevant files/docs: <list known files, docs, screenshots, logs, API examples, hardware details>
- Related routes/APIs: <list endpoints, response examples, scopes, public/private boundary>
- Related services/scripts: <systemd units, install/upgrade/uninstall/support scripts>
- Hardware/OS details: <Raspberry Pi model, Raspberry Pi OS/Debian/Ubuntu version, camera model, SDK/tool versions>
- Known constraints: <timeouts, permissions, data preservation, mobile compatibility, local-first requirements>

Non-goals:
- <explicitly list what must not be changed>
- <include unrelated layers to avoid scope creep>

Project-specific rules:
- Follow docs/AGENT_GUIDELINES.md.
- Preserve Raspberry Pi/Linux-first and local-first behavior.
- Keep the REST API under `/api/v1` with stable response envelopes.
- Preserve API key scopes and mobile-client compatibility.
- Preserve systemd/install/upgrade/uninstall/support behavior unless explicitly in scope.
- Preserve existing user data, images, config, database, logs, generated products, and Allsky source data.
- Use camera adapter interfaces for hardware work.
- Do not present mock, scaffolded, or placeholder hardware support as complete.
- Do not add hidden cloud dependencies.
- Do not revert, overwrite, delete, or undo unrelated work.
- Do not use destructive Git commands.
- Prefer additive, targeted patches over rewrites.

Required workflow:
1. Planner
   - Run `git status --short` before edits.
   - Inspect relevant files before proposing changes.
   - Identify uncommitted user/team work.
   - Identify affected layers and non-goals.
   - Identify whether Context7 MCP is needed.
   - Define acceptance criteria and validation commands.

2. Engineer
   - Define the technical design and contracts.
   - Reuse existing patterns and interfaces.
   - Identify edge cases, compatibility concerns, and failure behavior.

3. Developer
   - Implement only the scoped changes.
   - Add/update tests and docs when behavior changes.
   - Avoid broad formatting or unrelated cleanup.

4. Reviewer
   - Run `git diff --stat` and `git diff` before finishing.
   - Check acceptance criteria and layer boundaries.
   - Check Raspberry Pi, API, UI, installer/systemd, camera, migration, and security impact as relevant.
   - Run validation or explain why it was not run.

Acceptance criteria:
1. <observable outcome 1>
2. <observable outcome 2>
3. <observable outcome 3>
4. <test/doc/API/UX/security requirement if relevant>

Verification rubric:
- Deterministic tests: <unit/integration/build/lint commands and expected results>
- Contract checks: <OpenAPI, response envelope, scopes, public disabled behavior, migration preview, etc.>
- Manual review: <UI flow, systemd behavior, camera behavior, installer dry run, logs, screenshots>
- Regression checks: <specific existing behavior that must still work>
- If non-deterministic/agent behavior is involved: <eval cases, scoring rubric, trajectory/tool-use expectations>

Suggested validation:
```bash
git status --short
backend\.venv\Scripts\python -m pytest backend\tests
npm run lint
npm test
npm run build
```

Linux/Raspberry Pi validation when relevant:
```bash
backend/.venv/bin/python -m pytest backend/tests
bash scripts/test_install.sh
bash -n install.sh scripts/test_install.sh upgrade.sh uninstall.sh support.sh
shellcheck install.sh scripts/test_install.sh upgrade.sh uninstall.sh support.sh
```

Expected final response:
Task completed: <short summary>

Planner:
- <plan summary, operating mode, affected layers, non-goals>

Engineer:
- <design summary and contracts>

Developer:
- <implementation summary>

Reviewer:
- <pass/pass with notes/needs changes and review findings>

Changed files:
- <file list>

Validation:
- <commands run and results>

Notes:
- <limitations, assumptions, unrelated local changes, Context7 status, remaining risks>
````

## Task Author Checklist

Before handing a task to an agent, make sure the prompt answers:

- What exact behavior should change?
- What behavior must not change?
- Which layer or layers are in scope?
- How will the agent know it is done?
- Which tests/build/lint checks should run?
- What project data must be preserved?
- Is this exploratory prototype work or production-grade work?
- Does the task require current dependency docs through Context7?

## Common Task Variants

### Backend/API Task

Add these constraints:

```text
- Keep endpoints under `/api/v1`.
- Preserve response envelope shape.
- Enforce API key scopes.
- Keep future mobile clients in mind.
- Update OpenAPI-facing models/docs/examples when contracts change.
- Keep hardware-touching and long-running work daemon/queue owned when practical.
- Add backend tests for auth, scope boundaries, error cases, and important response shapes.
```

Suggested validation:

```bash
backend\.venv\Scripts\python -m pytest backend\tests
```

Acceptance criteria examples:

```text
1. The route returns the existing success/error envelope shape.
2. Unauthorized and insufficient-scope requests fail with the expected status and body.
3. OpenAPI docs reflect the new request/response contract.
4. Existing clients using previous fields remain compatible, or the breaking change is explicitly documented.
```

### Camera/Capture Task

Add these constraints:

```text
- Use camera adapter interfaces.
- Keep mock and hardware adapters separate.
- Use subprocess argument arrays, not shell strings.
- Keep browser code away from camera commands.
- Keep long-running captures daemon/queue owned when practical.
- Preserve queue pause/resume/stop, heartbeat, stale lock recovery, and interrupted job recovery semantics.
- Preserve Raspberry Pi service-user permissions and systemd behavior.
- Do not claim unvalidated hardware support is complete.
```

Suggested validation:

```bash
backend\.venv\Scripts\python -m pytest backend\tests\test_camera.py backend\tests\test_capture_daemon.py
```

Acceptance criteria examples:

```text
1. Mock camera behavior still works for development and CI.
2. Hardware adapter errors are actionable when tools/SDKs are missing.
3. Capture requests do not execute shell strings from browser/API input.
4. Daemon queue ownership and cancellation semantics are preserved.
```

### Installer/Systemd Task

Add these constraints:

```text
- Preserve existing user data.
- Keep scripts idempotent.
- Support dry-run behavior where possible.
- Do not delete config, database, logs, images, generated products, or Allsky data without explicit confirmation.
- Keep sudoers permissions narrow.
- Keep service units restartable and observable through systemd.
- Consider Raspberry Pi OS Bookworm first while retaining Debian/Ubuntu development support.
```

Suggested validation:

```bash
bash scripts/test_install.sh
bash -n install.sh scripts/test_install.sh upgrade.sh uninstall.sh support.sh
shellcheck install.sh scripts/test_install.sh upgrade.sh uninstall.sh support.sh
```

Acceptance criteria examples:

```text
1. Re-running install preserves `/etc/skyweaver/skyweaver.env`.
2. Dry-run mode reports actions without writing system files.
3. Unit changes keep `skyweaver.target`, API, capture, and worker services restartable.
4. Sudoers changes are narrow and validated.
```

### Web UI Task

Add these constraints:

```text
- Keep UI behavior backed by real API contracts.
- Do not present scaffolded backend features as complete.
- Preserve mobile-friendly layouts.
- Keep operational tools dense, clear, and repeat-use friendly.
- Show accurate loading, disabled, empty, permission, and error states.
- Do not put camera commands, service shell commands, or filesystem assumptions in browser code.
```

Suggested validation:

```bash
npm run lint
npm test
npm run build
```

Acceptance criteria examples:

```text
1. The UI calls the intended `/api/v1` endpoint and handles its documented response envelope.
2. Mobile layout remains usable.
3. Public disabled states and auth failures are represented accurately.
4. No fake success state is shown for scaffolded backend behavior.
```

### Image Processing/Product Task

Add these constraints:

```text
- Keep processing worker ownership clear.
- Preserve generated product storage paths and public/latest artifact behavior.
- Avoid blocking API handlers with long-running ffmpeg or image-processing work.
- Keep failures visible in job status/logs.
- Preserve existing thumbnails, keograms, timelapses, mini timelapses, and startrails unless explicit migration is in scope.
```

Suggested validation:

```bash
backend\.venv\Scripts\python -m pytest backend\tests
```

### Public Page/Public API Task

Add these constraints:

```text
- Preserve unauthenticated public page behavior.
- Honor the public-page enabled setting.
- Keep `/api/v1/public/latest` and related download/thumbnail endpoints compatible.
- Public clients should receive the documented disabled-state behavior when public mode is off.
- Do not leak private/admin-only data through public endpoints.
```

Suggested validation:

```bash
backend\.venv\Scripts\python -m pytest backend\tests
npm run lint
npm test
npm run build
```

### Allsky Migration Task

Add these constraints:

```text
- Detect and preview before importing.
- Never mutate original Allsky data by default.
- Report unsupported settings.
- Rollback only Sky Weaver-created rows/files.
- Preserve images, products, dark frames, overlays, location, camera hints, and public-page intent where possible.
- Keep scaffolded behavior labeled as scaffolded until real import/rollback is implemented and validated.
```

Suggested validation:

```bash
backend\.venv\Scripts\python -m pytest backend\tests
```

Acceptance criteria examples:

```text
1. Detection reports likely Allsky sources without modifying them.
2. Dry-run preview reports counts, unsupported settings, and import plan.
3. Import preserves original files and records provenance for rollback.
4. Rollback only removes Sky Weaver-created rows/files.
```

### Documentation-Only Task

Add these constraints:

```text
- Keep docs accurate to current implementation.
- Label future/scaffolded behavior clearly.
- Update examples when commands, paths, routes, or service names change.
- Prefer concise, operator-useful docs over broad marketing copy.
```

Suggested validation:

```bash
git diff --stat
git diff
```

## Anti-Patterns To Call Out In Reviews

- Prompt-only “fixes” without repository inspection.
- Accepting generated code because it looks plausible.
- New dependencies that were not checked against real package docs.
- UI claiming a backend, camera, migration, or upload feature is complete when it is scaffolded.
- Hardware commands reachable from browser code.
- Installer changes that are not idempotent or data-safe.
- API responses that silently break mobile/client compatibility.
- Repeated test-fix loops without root-cause analysis.
- Broad rewrites or formatting changes unrelated to the task.
