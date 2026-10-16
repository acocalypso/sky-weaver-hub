# Dependency Maintenance

Last refreshed: 2026-10-16, starting from source baseline `1db48f4`.

## Runtime requirements

- Python 3.11+; the updated Pydantic Settings package requires 3.11. Raspberry Pi OS Bookworm meets this requirement.
- Node matching `^22.22.2 || ^24.15.0 || >=26.0.0`; Node 24 is recommended and used in CI. Local verification now uses Node 24.22.0, the existing Python 3.12.10 virtualenv, and an isolated Python 3.15.0 environment on Windows.
- The installer obtains Node/npm from configured apt repositories. It does not bootstrap a compatible Node release if the available package is too old. Check the runtime before install/upgrade.

## October 2026 refresh

Direct package versions were checked against the npm registry and PyPI stable releases: 58 direct npm versions and seven direct Python pins changed from the source baseline, including jsdom after the local Node upgrade. Existing exact pins and caret range styles are preserved, and `package-lock.json` is regenerated. Backend direct requirements remain exact pins; their transitive dependencies remain resolver-selected rather than fully locked.

Selected frontend/tooling updates:

| Package | Previous | Updated |
| --- | --- | --- |
| React / React DOM | 19.2.7 | 19.3.1 |
| Vite | 8.1.0 | 8.3.4 |
| React Vite plugin | 6.0.3 | 6.1.2 |
| Vitest | 4.1.9 | 5.0.5 |
| Testing Library jest-dom | 6.9.1 | 7.0.1 |
| jsdom | 29.1.1 | 30.1.3 |
| Playwright | 1.61.1 | 1.64.1 |
| Tailwind CSS / Vite plugin | 4.3.1 | 4.3.3 |
| React Query | 5.101.1 | 5.104.3 |
| React Hook Form / resolvers | 7.80.0 / 5.4.0 | 7.90.0 / 5.9.1 |
| Recharts | 3.9.0 | 3.10.1 |
| ESLint / typescript-eslint | 10.5.0 / 8.62.0 | 10.12.0 / 8.71.2 |

Radix components, React types, routing, icons, form/schema helpers and other packages with compatible stable updates were refreshed too. The manifests and lockfile are the complete version record.

Backend updates:

| Package | Previous | Updated |
| --- | --- | --- |
| FastAPI | 0.138.0 | 0.143.2 |
| Uvicorn | 0.49.0 | 0.54.0 |
| Pydantic Settings | 2.14.2 | 2.16.0 |
| PyJWT | 2.13.0 | 2.15.1 |
| cryptography | 46.0.3 | 50.0.2 |
| Pillow | 12.2.0 | 12.3.0 |
| httpx2 | 2.4.0 | 2.13.1 |

Other direct Python requirements were already current at the registry check. Compatible transitive Python packages were refreshed in the local virtualenv. Published Linux ARM64 wheels were confirmed for cryptography 50.0.2 and Pillow 12.3.0; that check does not substitute for installation or camera acceptance on a Pi.

## Compatibility decisions

- **TypeScript stays at 6.0.3.** Although 7.0.2 is published, typescript-eslint 8.71.2 declares a TypeScript peer range of `>=4.8.4 <6.1.0`. Upgrade the compiler after compatible lint tooling is available.
- **jsdom is now 30.1.3.** Its Node range is `^22.22.2 || ^24.15.0 || >=26.0.0`. The upgrade was verified after the local runtime moved to Node 24.22.0, and the project's engine range now reflects that requirement.
- **Typography parser override:** `@tailwindcss/typography` 0.5.20 still selects the vulnerable parser 6.x. A narrowly scoped npm override selects `postcss-selector-parser ^7.1.6`. Remove the override when typography itself declares a fixed compatible parser. The dependency refresh must validate Tailwind typography generation as well as the application build.
- Vite/Vitest aliases use `import.meta.dirname` instead of `__dirname`, removing the new Vite native-config-loader warning without changing the alias destination.
- Test setup imports `@testing-library/jest-dom/vitest` explicitly so the matcher types augment Vitest 5's assertions correctly.

Context7 was used for Vite 8/plugin compatibility, FastAPI upgrade/testing guidance, and Vitest 5 migration requirements. Package registry engine/peer metadata determined the precise versions and holdbacks. Relevant primary references: [Vite 8](https://vite.dev/blog/announcing-vite8), [FastAPI version upgrades](https://fastapi.tiangolo.com/deployment/versions/), [Vitest migration](https://vitest.dev/guide/migration), [cryptography release changes](https://cryptography.io/en/latest/changelog/), and [selector parser releases](https://github.com/postcss/postcss-selector-parser/releases/tag/v7.0.0).

The runtime follow-up also checked jsdom's Node requirements through Context7 and the registry. Python pins were rechecked against PyPI and remained current. Python 3.15 installation succeeded in `.tmp/python315-verification`; PyYAML 6.0.3 required a local wheel build because a matching prebuilt wheel was unavailable. `backend/.venv` remains on Python 3.12.10; updating global Python does not retarget an existing virtualenv. Production's Python 3.11+ requirement is unchanged.

## Validation

Local checks after the refresh:

- `npm ci --prefer-offline`: passed with the regenerated lockfile.
- `npm ls --all --json`: no dependency-tree problems; locked Node engine ranges also accept the declared 22.22.2, 24.15.0 and 26.0.0 floors and local 24.22.0.
- `npm audit --audit-level=low`: zero reported vulnerabilities.
- `npm run lint`, `npm test` and `npm run build`: passed; **41 frontend tests** after the correctness follow-up.
- `npx playwright install chromium` and `npm run test:smoke`: **11 passed, 1 intentional skip** (mobile-only case on the desktop project).
- Direct Tailwind typography compilation: prose, size, invert and heading CSS generated successfully; trailing-pseudo selector parsing passed with the parser override.
- `backend\.venv\Scripts\python.exe -m pip check`: no broken requirements.
- `backend\.venv\Scripts\python.exe -m pytest backend/tests -q`: **142 passed, 1 skipped** on Python 3.12.10 (POSIX permission diagnostics on Windows). The full suite also passed with **142 passed, 1 skipped** using `.tmp/python315-verification/Scripts/python.exe` on Python 3.15.0.
- Isolated OpenAPI generation: **96 paths**, JSON output generated successfully.
- `npx tsc -p tsconfig.node.json --noEmit`: passed.
- `npm run typecheck`: passes after the correctness follow-up repaired the 36 pre-existing diagnostics in UI wrappers, page typings and the ES library target. See [correctness review](CORRECTNESS_REVIEW.md) for the related runtime fixes and regression coverage.

No new Raspberry Pi, shell installer or overnight/hardware acceptance was performed. Hardware/overnight acceptance is separate from local build, API and browser checks.

For subsequent refreshes, run the frontend lint, unit tests, production build and Playwright smoke suite; backend tests, `pip check` and OpenAPI generation; and inspect `npm audit`, peer dependencies and runtime engines. Refresh Playwright's Chromium binary when upgrading Playwright. Avoid forced major upgrades solely to silence the audit command.
