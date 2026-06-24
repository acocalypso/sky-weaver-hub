# Sky Weaver Hub Agent Task Template

Use this template when assigning implementation work to Codex or a multi-agent coding team.

For dependency-specific work, report whether Context7 MCP was used and note any important documentation source, package version, or assumption that affected the implementation.


````text
# Task For GPT-5.5 Codex Multi-Agent Team

Repository: C:\Users\Aco\Desktop\Dev-Tools\sky-weaver-hub

Task:
<describe the concrete implementation task>

Context:
<add relevant project context, links, files, screenshots, logs, API examples, Raspberry Pi details, or constraints>

Project-specific rules:
- Follow docs/AGENT_GUIDELINES.md.
- Sky Weaver Hub is Raspberry Pi/Linux first and local-first.
- Keep the REST API under /api/v1 with stable response envelopes.
- Preserve systemd/install/upgrade/uninstall/support behavior.
- Preserve existing user data, images, config, database, and Allsky source data.
- Use camera adapter interfaces for hardware work.
- Do not present mock or placeholder hardware support as complete.
- Keep future Android/iOS API clients in mind.

Layer boundaries:
- Web UI
- REST API
- database/storage
- capture daemon
- camera adapters
- image processing worker
- installer/systemd scripts
- migration tools

Important constraints:
- Use the Planner -> Engineer -> Developer -> Reviewer workflow.
- Do not revert, overwrite, delete, or undo unrelated work.
- Do not use destructive Git commands.
- Preserve all existing user/team changes.
- Keep the implementation scoped to this task.
- Prefer additive, targeted patches over rewrites.
- Do not mix frontend UI changes with backend/capture rewrites unless this task explicitly requires it.
- Run relevant tests/build/lint checks.
- Report changed files and validation results.

Acceptance criteria:
1. <criterion 1>
2. <criterion 2>
3. <criterion 3>

Suggested validation:
```bash
git status --short
backend\.venv\Scripts\python -m pytest backend\tests
npm run lint
npm test
npm run build
```

Add task-specific validation when relevant:
```bash
bash scripts/test_install.sh
bash -n install.sh scripts/test_install.sh upgrade.sh uninstall.sh support.sh
shellcheck install.sh scripts/test_install.sh upgrade.sh uninstall.sh support.sh
```

Expected final response:
- Planner summary
- Engineer design summary
- Developer implementation summary
- Reviewer result
- Changed files
- Commands run
- Test/build results
- Known limitations
````

## Common Task Variants

### Backend/API Task

Add these constraints:

```text
- Keep endpoints under /api/v1.
- Preserve response envelope shape.
- Enforce API key scopes.
- Update API docs/OpenAPI-facing behavior when contracts change.
- Add backend tests for auth, scope boundaries, and important response shapes.
```

Suggested validation:

```bash
backend\.venv\Scripts\python -m pytest backend\tests
```

### Camera/Capture Task

Add these constraints:

```text
- Use camera adapter interfaces.
- Keep mock and hardware adapters separate.
- Use subprocess argument arrays, not shell strings.
- Keep long-running captures daemon/queue owned when practical.
- Preserve Raspberry Pi service-user permissions and systemd behavior.
```

Suggested validation:

```bash
backend\.venv\Scripts\python -m pytest backend\tests\test_camera.py backend\tests\test_capture_daemon.py
```

### Installer/Systemd Task

Add these constraints:

```text
- Preserve existing user data.
- Keep scripts idempotent.
- Support dry-run behavior where possible.
- Do not delete config, database, logs, images, or Allsky data without explicit confirmation.
- Keep sudoers permissions narrow.
```

Suggested validation:

```bash
bash scripts/test_install.sh
bash -n install.sh scripts/test_install.sh upgrade.sh uninstall.sh support.sh
shellcheck install.sh scripts/test_install.sh upgrade.sh uninstall.sh support.sh
```

### Web UI Task

Add these constraints:

```text
- Keep UI behavior backed by real API contracts.
- Do not present scaffolded backend features as complete.
- Preserve mobile-friendly layouts.
- Keep operational tools dense, clear, and repeat-use friendly.
```

Suggested validation:

```bash
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
```

Suggested validation:

```bash
backend\.venv\Scripts\python -m pytest backend\tests
```
