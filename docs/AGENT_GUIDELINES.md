# Sky Weaver Hub Agent Guidelines

Sky Weaver Hub is a Raspberry Pi/Linux-first, local-first all-sky camera platform and a modern successor path for users of AllskyTeam/allsky. Every implementation, review, documentation, and automation agent must protect that direction.

This file is the project’s **static agent harness**: the always-loaded rules that keep AI-assisted development disciplined. Keep it concise enough to remain high-signal. Put task-specific details, logs, screenshots, issue text, and temporary investigation notes in the task prompt or companion docs instead of bloating this file.

## Operating Principle: Agentic Engineering, Not Vibe Coding

Use AI agents as implementation engines inside a controlled engineering system. Do not rely on “it seems to work.” Production work requires clear intent, repository inspection, scoped changes, deterministic validation, and human-reviewable evidence.

For Sky Weaver Hub, agentic engineering means:

- **Specification before generation:** define the task, non-goals, affected layers, contracts, and acceptance criteria before editing.
- **Context before code:** inspect relevant project files and current dependency docs before proposing dependency-specific changes.
- **Verification before confidence:** run relevant tests/build/lint checks, or state exactly why they could not be run.
- **Review before final:** inspect the diff and final behavior against the acceptance criteria.
- **Human judgment stays in charge:** architecture, safety, migration semantics, hardware claims, and release readiness must remain reviewable by a human maintainer.

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

If priorities conflict, choose the earlier priority and document the trade-off.

## Project Snapshot Agents Must Preserve

Sky Weaver Hub currently includes:

- Vite/React admin UI backed by the local `/api/v1` service.
- FastAPI backend with SQLite storage.
- Bootstrap admin login, first-setup flow, and API-key-ready auth model.
- Mock camera adapter plus rpicam/libcamera and ZWO ASI adapter paths.
- Daemon-owned capture queue with scheduled capture, pause/resume/stop semantics, heartbeat, stale lock recovery, and interrupted job recovery.
- Processing worker for thumbnails, keograms, timelapses, mini timelapses, and startrails.
- Public unauthenticated sky page and public latest-image API guarded by the public-page enabled setting.
- System Health UI with service control, journal inspection, diagnostics export, and queue/metric summaries.
- Installer/systemd scripts for Raspberry Pi deployment.
- Allsky migration detection and dry-run preview, with real import/rollback still intentionally scaffolded.

Do not describe scaffolded areas as complete. When changing behavior, update docs and API-facing contracts so the project state remains honest.

## Static vs Dynamic Context

Use this file for stable, always-applicable rules. Load dynamic context only when relevant:

- **Repository files:** read the actual implementation before editing.
- **Task packet:** use the user’s task, acceptance criteria, logs, screenshots, hardware details, and constraints.
- **Dependency docs:** use Context7 MCP for third-party APIs and packages.
- **Specialized knowledge:** load layer-specific docs, migration notes, API docs, camera docs, installer docs, or security docs only when the task touches those areas.
- **Validation output:** use test/build/lint results as feedback, not as decoration.

Avoid dumping entire unrelated files into the prompt. Prefer small, relevant excerpts and concrete file paths.

## Documentation Freshness And Context7 MCP

When working with third-party libraries, frameworks, APIs, SDKs, package configuration, or dependency-specific implementation details, use the Context7 MCP server before proposing or changing code.

Required rules:

- Prefer current Context7 documentation over built-in model knowledge for external dependencies.
- Use Context7 before implementing or reviewing changes involving React, Vite, FastAPI, Pydantic, SQLAlchemy, pytest, npm packages, Python packages, Raspberry Pi camera tooling, Android/iOS-related tooling, or other external APIs.
- Do not rely on outdated examples when library behavior, configuration syntax, CLI flags, or APIs may have changed.
- If Context7 is unavailable, say so explicitly and continue only with repository inspection and clearly stated assumptions.
- Mention relevant documentation sources, package versions, or assumptions in the plan, review notes, or final response when they affected the implementation.
- Context7 supplements repository inspection; it does not replace reading the actual project files before editing.

## Agent Operating Modes

Choose the lowest-autonomy mode that fits the risk.

### Conductor Mode

Use for ambiguous, risky, architectural, hardware-facing, security-sensitive, installer/systemd, migration, or production-breaking work. The agent should make small changes, surface decisions early, and preserve human control.

### Orchestrator Mode

Use for well-specified, bounded tasks with clear tests and existing patterns. The agent may handle multi-file changes, but must still plan, inspect, validate, and review.

### Background/Delegated Mode

Use only for tasks that are narrow, reproducible, and easy to validate, such as adding tests for an existing contract, applying a repeated pattern, or updating documentation. The task prompt must include explicit acceptance criteria and validation commands.

Never use high-autonomy execution for work that lacks a clear rollback path or touches user data, hardware commands, auth, installer privileges, or migration behavior.

## Required Workflow

Use this role sequence for implementation tasks:

1. Planner
2. Engineer
3. Developer
4. Reviewer

For small fixes, the roles can be summarized briefly, but the thinking still has to happen.

### Planner

Planner responsibilities:

- Read the request, the task packet, and relevant project docs.
- Run `git status --short` before edits.
- Identify existing uncommitted changes as user/team work.
- Inspect current implementation before proposing changes.
- Identify whether Context7 or other dependency docs are required.
- Define affected layers and files.
- Define non-goals to prevent scope creep.
- Define acceptance criteria and validation commands.
- Identify Raspberry Pi, installer, API, mobile, security, data, and migration risks.

Planner output should include:

- Task summary.
- Operating mode: conductor, orchestrator, or background/delegated.
- Affected areas.
- Non-goals.
- Implementation steps.
- Acceptance criteria.
- Test/eval plan.
- Risks or assumptions.

### Engineer

Engineer responsibilities:

- Convert the plan into a concrete technical design.
- Prefer existing interfaces and local patterns.
- Keep public API and mobile-client compatibility in mind.
- Avoid rewrites unless the task requires them.
- Define data, API, daemon, adapter, UI, installer, or migration contracts clearly.
- Define failure behavior and edge cases.
- Note backwards compatibility and migration behavior.

Engineer output should include:

- Technical design.
- Files/modules to modify.
- Interfaces/contracts to add or change.
- Edge cases.
- Compatibility notes.
- Validation strategy.

### Developer

Developer responsibilities:

- Implement only the agreed scope.
- Use targeted patches.
- Preserve existing behavior unless the task explicitly changes it.
- Do not delete, revert, overwrite, or mass-format unrelated work.
- Add or update tests when behavior changes.
- Add comments only for non-obvious logic.
- Re-read files immediately before editing if other changes may exist.
- Avoid dependency additions unless justified and documented.

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
- Check hallucinated dependencies, incorrect imports, dead code, and error handling gaps.
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

## Architecture Boundaries

Keep implementation layers separated:

- Web UI: React/Vite pages, components, routing, browser UX, and client-side state.
- REST API: FastAPI routes under `/api/v1`, auth, scopes, response envelopes, OpenAPI, SSE.
- Database/storage: SQLite schema, migrations, filesystem paths, image/product/log/config storage.
- Capture daemon: scheduled capture loop, capture queue ownership, heartbeat, job recovery, cancellation semantics.
- Camera adapters: mock, rpicam/libcamera, ZWO, gPhoto2, V4L2/webcam, INDI, custom command.
- Image processing worker: thumbnails, keograms, timelapses, startrails, future overlays/dark frames.
- Installer/systemd scripts: install, upgrade, uninstall, support, units, sudoers, dry-run behavior.
- Migration tools: Allsky detection, preview, import, rollback, unsupported-setting reports.
- Public surface: `/public`, public latest-image APIs, unauthenticated assets, and disabled-state behavior.

Do not mix frontend UI changes with backend/capture rewrites unless the task explicitly requires both. If a feature spans layers, keep each layer’s contract clear and test the boundary.

## API Work Rules

REST API work must:

- Keep endpoints under `/api/v1` unless intentionally serving public static assets or docs.
- Preserve the stable success/error envelope.
- Enforce API key scopes and auth boundaries.
- Keep future Android/iOS clients in mind.
- Avoid breaking response fields without a compatibility reason.
- Update OpenAPI-facing types, examples, and docs when contracts change.
- Add tests for authorization, scope boundaries, and important response shapes.
- Keep long-running hardware or processing work daemon/queue owned whenever practical.

API handlers should return jobs quickly and let workers/daemons perform long-running work.

## Camera And Capture Work Rules

All camera work must use adapter interfaces.

Required rules:

- Keep mock, rpicam/libcamera, ZWO, gPhoto2, V4L2/webcam, INDI, and custom-command adapters separate.
- Do not present placeholder adapters as complete hardware support.
- Avoid shell injection.
- Prefer subprocess argument arrays over shell strings.
- Keep browser code away from direct camera commands.
- Preserve mock camera behavior for development and CI.
- Add actionable errors when hardware tools or SDKs are missing.
- Keep capture queue ownership in the daemon when practical.
- Preserve cancellation, heartbeat, stale lock recovery, and interrupted job recovery semantics.

For Raspberry Pi camera work:

- Prefer `rpicam-*` commands with compatibility for `libcamera-*` naming where practical.
- Consider service-user permissions, video/render/input groups, `/dev/media*`, DMA heap, and systemd unit environment.
- Do not assume behavior verified on Windows also works on Raspberry Pi.

## Installer And Systemd Rules

Installer/systemd work must:

- Preserve existing user data.
- Be idempotent.
- Support dry-run mode where possible.
- Never delete images, config, database, logs, imported Allsky data, or generated products without explicit confirmation.
- Keep services restartable through systemd.
- Keep constrained sudoers permissions narrow and validated.
- Keep `install.sh`, `upgrade.sh`, `uninstall.sh`, and `support.sh` shellcheck-friendly.
- Consider Raspberry Pi OS Bookworm first, while retaining Debian/Ubuntu development support.
- Preserve `/etc/skyweaver/skyweaver.env` unless the task explicitly changes configuration migration behavior.

## Migration Rules

Allsky migration work must:

- Detect and preview before import.
- Never mutate or delete original Allsky data by default.
- Report unsupported settings.
- Keep rollback limited to Sky Weaver-created rows/files.
- Preserve user images, videos, keograms, startrails, dark frames, overlay assets, location/camera hints, and public-page intent where possible.
- Keep scaffolded import/rollback behavior clearly labeled until it is real and validated.

## Web UI Rules

Web UI work must:

- Use real API contracts; do not fake backend capability in the UI.
- Preserve mobile-friendly layouts and repeat-use operator workflows.
- Treat the Health, capture, camera, settings, public-page, and migration views as operational tools, not decorative demos.
- Show accurate disabled, loading, permission, and error states.
- Keep browser code away from camera commands, service control shell commands, and filesystem assumptions.

## Security And Local-First Rules

Security-sensitive work must:

- Avoid hard-coded secrets, default credentials beyond documented bootstrap flows, and accidental token logging.
- Preserve API key scope boundaries.
- Avoid hidden external network dependencies.
- Make optional cloud/upload integrations explicit, configurable, and disabled by default unless the project owner says otherwise.
- Validate subprocess arguments and paths.
- Treat generated code as untrusted until reviewed and tested.
- Check new dependencies for real package names, maintenance status, and necessity.

## Verification, Tests, And Evals

Tests verify deterministic behavior. Evals or review rubrics verify non-deterministic or workflow behavior. Use both where relevant.

For normal code changes:

- Add or update unit/integration tests when behavior changes.
- Run the smallest relevant validation first, then broader checks when risk justifies it.
- If validation fails, diagnose root cause before retrying. Do not loop blindly on error messages.
- Report exact commands and results.

For AI-agent features, generated workflows, or non-deterministic behavior:

- Define a rubric before implementation.
- Evaluate tool-use quality, trajectory compliance, final output quality, hallucination risk, and safety boundaries.
- Add regression cases for any failure the agent fixes.

## Suggested Validation

Choose commands relevant to the task.

Common checks:

```bash
git status --short
backend\.venv\Scripts\python -m pytest backend\tests
npm run lint
npm test
npm run build
bash scripts/test_install.sh
bash -n install.sh scripts/test_install.sh upgrade.sh uninstall.sh support.sh
```

On Linux/Raspberry Pi:

```bash
backend/.venv/bin/python -m pytest backend/tests
shellcheck install.sh scripts/test_install.sh upgrade.sh uninstall.sh support.sh
```

For API contract changes, also validate OpenAPI generation and any documented client examples.

## Review Checklist

Every reviewer must specifically check:

- Did this regress Raspberry Pi deployment?
- Did this introduce hidden cloud/network dependency?
- Did this regress REST API compatibility?
- Did this regress public API/page disabled-state behavior?
- Did this regress existing WebUI behavior?
- Did this preserve unrelated user/team changes?
- Did it keep layers separate?
- Did camera work use adapters and safe subprocess calls?
- Did installer work preserve data and idempotency?
- Did migration work preserve original Allsky data?
- Did docs/project state change when behavior changed?
- Were relevant tests/build/lint checks run?
- Are scaffolded features still honestly described as scaffolded?
- Are dependencies real, necessary, and documented?

## Definition Of Done

A task is done only when:

1. The requested behavior is implemented within scope.
2. Existing user/team changes are preserved.
3. Layer boundaries and product priorities are respected.
4. Relevant tests/docs/contracts are updated.
5. Validation was run or a clear reason is provided.
6. The diff was reviewed.
7. Remaining risks and assumptions are stated.

## Final Response Format

Use this structure for implementation tasks:

```text
Task completed: <short summary>

Planner:
- <what was planned, including operating mode and affected layers>

Engineer:
- <technical approach and contracts>

Developer:
- <what was implemented>

Reviewer:
- <review result and issues found>

Changed files:
- <file list>

Validation:
- <commands run and results>

Notes:
- <limitations, assumptions, unrelated local changes, or follow-up work>
```

For very small fixes, this can be concise, but it should still report changed files and validation.
