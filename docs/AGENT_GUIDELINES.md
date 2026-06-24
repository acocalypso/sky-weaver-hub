# Sky Weaver Hub Agent Guidelines

Sky Weaver Hub is a Raspberry Pi/Linux first, local-first all-sky camera platform and a modern successor path for users of AllskyTeam/allsky. Every implementation agent must preserve that direction.

These rules apply to all coding, review, documentation, and automation work in this repository.

## Product Priorities

Implementations must respect these priorities, in this order:

1. Raspberry Pi/Linux first.
2. Local-first operation with no hidden cloud dependency.
3. Real installer and systemd support.
4. REST API first.
5. Future Android/iOS app compatibility.
6. Modern WebUI.
7. Hardware adapter abstraction.
8. No fake hardware support presented as complete.
9. Mock camera only for development, tests, demos, and CI.
10. Existing Allsky users need a safe migration path.

## Architecture Boundaries

Keep implementation layers separated:

- Web UI: React/Vite pages, components, routing, and browser UX.
- REST API: FastAPI routes under `/api/v1`, auth, scopes, response envelopes, OpenAPI.
- Database/storage: SQLite schema, filesystem paths, image/product/log/config storage.
- Capture daemon: scheduled capture loop, capture queue ownership, heartbeat, job recovery.
- Camera adapters: mock, rpicam/libcamera, ZWO, gPhoto2, V4L2/webcam, INDI, custom command.
- Image processing worker: thumbnails, keograms, timelapses, startrails, future overlays/dark frames.
- Installer/systemd scripts: install, upgrade, uninstall, support, units, sudoers, dry-run behavior.
- Migration tools: Allsky detection, preview, import, rollback, unsupported-setting reports.

Do not mix frontend UI changes with backend/capture rewrites unless the task explicitly requires both. If a feature spans layers, keep each layer's contract clear and test the boundary.

## Required Workflow

Use this role sequence for implementation tasks:

1. Planner
2. Engineer
3. Developer
4. Reviewer

For small fixes, the roles can be summarized briefly, but the thinking still has to happen.

### Planner

Planner responsibilities:

- Read the request and relevant project docs.
- Run `git status --short` before edits.
- Identify existing uncommitted changes as user/team work.
- Inspect the current implementation before proposing changes.
- Define affected layers and files.
- Define acceptance criteria and validation commands.
- Identify Raspberry Pi, installer, API, mobile, and migration risks.

Planner output should include:

- Task summary.
- Affected areas.
- Implementation steps.
- Acceptance criteria.
- Test plan.
- Risks or assumptions.

### Engineer

Engineer responsibilities:

- Convert the plan into a concrete technical design.
- Prefer existing interfaces and local patterns.
- Keep public API and mobile-client compatibility in mind.
- Avoid rewrites unless the task requires them.
- Define data, API, daemon, adapter, or UI contracts clearly.
- Note backwards compatibility and migration behavior.

Engineer output should include:

- Technical design.
- Files/modules to modify.
- Interfaces/contracts to add or change.
- Edge cases.
- Compatibility notes.

### Developer

Developer responsibilities:

- Implement only the agreed scope.
- Use targeted patches.
- Preserve existing behavior unless the task explicitly changes it.
- Do not delete, revert, overwrite, or mass-format unrelated work.
- Add or update tests when behavior changes.
- Add comments only for non-obvious logic.
- Re-read files immediately before editing if other changes may exist.

Developer output should include:

- Implementation summary.
- Changed files.
- Tests added or updated.
- Deviations from plan, if any.

### Reviewer

Reviewer responsibilities:

- Review the final diff before finishing.
- Check acceptance criteria.
- Check Raspberry Pi deployment impact.
- Check REST API compatibility and stable response shape.
- Check existing UI behavior.
- Check installer/systemd safety if scripts or service behavior changed.
- Check camera adapter separation and subprocess safety for camera work.
- Check that unrelated user/team changes were preserved.
- Run relevant validation or state exactly why it was not run.

Reviewer output should include:

- Result: pass, pass with notes, or needs changes.
- Issues found.
- Required fixes, if any.
- Validation results.
- Remaining risks.

## Repository Safety

Before making changes:

```bash
git status --short
```

Treat any existing uncommitted changes as user/team work. Do not revert or overwrite them.

Never run destructive Git commands unless the user explicitly requests them:

- `git reset --hard`
- `git checkout -- .`
- `git clean -fd`
- force-push
- rebase or amend without explicit instruction

Prefer additive, targeted fixes over broad rewrites.

Before finishing:

```bash
git diff --stat
git diff
```

Review the diff and confirm it contains only task-related changes.

## Camera Work Rules

All camera work must use adapter interfaces.

Required rules:

- Keep mock, rpicam/libcamera, ZWO, gPhoto2, V4L2/webcam, INDI, and custom-command adapters separate.
- Do not present placeholder adapters as complete hardware support.
- Avoid shell injection.
- Prefer subprocess argument arrays over shell strings.
- Keep browser code away from direct camera commands.
- Preserve mock camera behavior for development and CI.
- Add actionable errors when hardware tools or SDKs are missing.

For Raspberry Pi camera work:

- Prefer `rpicam-*` commands with compatibility for `libcamera-*` naming where practical.
- Consider service-user permissions, video/render/input groups, `/dev/media*`, DMA heap, and systemd unit environment.
- Do not assume behavior verified on Windows also works on Raspberry Pi.

## API Work Rules

REST API work must:

- Keep endpoints under `/api/v1`.
- Preserve the stable success/error envelope.
- Enforce API key scopes.
- Keep mobile clients in mind.
- Avoid breaking response fields without a compatibility reason.
- Update OpenAPI-facing types and docs when contracts change.
- Add tests for authorization, scope boundaries, and important response shapes.

Hardware-touching capture requests should be daemon/queue owned whenever practical. API handlers should return jobs quickly and let workers/daemons perform long-running work.

## Installer And Systemd Rules

Installer/systemd work must:

- Preserve existing user data.
- Be idempotent.
- Support dry-run mode where possible.
- Never delete images, config, database, logs, or imported Allsky data without explicit confirmation.
- Keep services restartable through systemd.
- Keep constrained sudoers permissions narrow and validated.
- Keep `install.sh`, `upgrade.sh`, `uninstall.sh`, and `support.sh` shellcheck-friendly.
- Consider Raspberry Pi OS Bookworm first, while retaining Debian/Ubuntu development support.

## Migration Rules

Allsky migration work must:

- Detect and preview before import.
- Never mutate or delete original Allsky data by default.
- Report unsupported settings.
- Keep rollback limited to Sky Weaver-created rows/files.
- Preserve user images, videos, keograms, startrails, dark frames, overlay assets, and location/camera hints where possible.

## Review Checklist

Every reviewer must specifically check:

- Did this regress Raspberry Pi deployment?
- Did this regress REST API compatibility?
- Did this regress existing WebUI behavior?
- Did this preserve unrelated user/team changes?
- Did it keep layers separate?
- Did camera work use adapters and safe subprocess calls?
- Did installer work preserve data and idempotency?
- Did docs/project state change when behavior changed?
- Were relevant tests/build/lint checks run?

## Suggested Validation

Choose commands relevant to the task:

```bash
git status --short
backend\.venv\Scripts\python -m pytest backend\tests
npm run lint
npm test
npm run build
bash scripts/test_install.sh
bash -n install.sh scripts/test_install.sh upgrade.sh uninstall.sh support.sh
```

On Linux/Raspberry Pi, use:

```bash
backend/.venv/bin/python -m pytest backend/tests
shellcheck install.sh scripts/test_install.sh upgrade.sh uninstall.sh support.sh
```

For API contract changes, also validate OpenAPI generation.

## Final Response Format

Use this structure for implementation tasks:

```text
Task completed: <short summary>

Planner:
- <what was planned>

Engineer:
- <technical approach>

Developer:
- <what was implemented>

Reviewer:
- <review result>

Changed files:
- <file list>

Validation:
- <commands run and results>

Notes:
- <limitations, assumptions, unrelated local changes, or follow-up work>
```

For very small fixes, this can be concise, but it should still report changed files and validation.
