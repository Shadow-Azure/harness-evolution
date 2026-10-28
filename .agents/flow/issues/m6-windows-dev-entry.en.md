# Fix Windows dev entry and local timezone dependency

English | [中文](m6-windows-dev-entry.md)

```yaml flow
kind: issue
id: m6-05
milestone: m6
depends: []
priority: P1
status: done
scope:
  - scripts/dev.mjs
  - apps/api/pyproject.toml
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 118
  url: https://github.com/Shadow-Azure/harness-evolution/issues/118
```

## Background

On a Windows 11 machine with Node.js 22, `pnpm dev` crashes outright: `scripts/dev.mjs` spawns `spawn("pnpm.cmd", …)` without `shell`, and since the CVE-2024-27980 fix Node refuses to spawn `.cmd`/`.bat` without a shell, throwing `spawn EINVAL` (Node ≥18.20/20.12/22). The roadmap m2 acceptance command is exactly "`pnpm dev` starts frontend and backend", so that entry point is entirely unusable on Windows. The same machine exposed a second independent defect: `app/utils/time.py` depends on `ZoneInfo("Asia/Shanghai")`, and Python on Windows ships no system zoneinfo database — without the `tzdata` PyPI package installed, any command importing that module (including `pnpm data:import:sessions`) dies with `ZoneInfoNotFoundError`. Additionally, the CLI entry check in `flow-new-issue.mjs`, `import.meta.url === \`file://${process.argv[1]}\``, is always false for Windows backslash paths so the script exits silently; that script is outside this issue's scope but is recorded in Verification as the same class of Windows compatibility defect.

## Goals

- `pnpm dev` starts both the API and Web child processes on Windows with Node ≥18.20/20.12/22, shuts both down on Ctrl+C, and behaves identically to POSIX.
- No manual `pip install tzdata` on Windows: the declared `apps/api` dependencies cover zoneinfo data, and `python -m app` plus every `python -m app.cli` command work out of the box.

## Design authority

- [plans/fullstack-design/10-roadmap-draft.md](../../../plans/fullstack-design/10-roadmap-draft.md): the m2 acceptance row "`pnpm dev` starts frontend and backend" — `dev.mjs` is the sole implementation of that command.
- [plans/fullstack-design/04-backend-architecture.md](../../../plans/fullstack-design/04-backend-architecture.md): the "timestamps unified to Asia/Shanghai" decision relies on `ZoneInfo("Asia/Shanghai")` resolving, which is what makes `tzdata` a declared dependency.
- Where implementation conflicts with the linked sections, the linked sections win; this issue only restores platform compatibility and changes no designed behavior.

## Implementation

- `scripts/dev.mjs`: the Windows branch of spawn gains `shell: true` (the POSIX branch keeps `spawn("pnpm", …)` unchanged) so the `.cmd` shim starts through a shell; signal forwarding and exit-code logic stay untouched.
- `apps/api/pyproject.toml`: declare `tzdata` among the runtime dependencies (version range bounded per repository convention, like every other dependency); on Linux/macOS the package merely acts as a fallback zoneinfo source and changes no behavior.

## Implementation steps

1. Change the spawn options in `scripts/dev.mjs`: when `process.platform === "win32"`, use `spawn(pnpm, [script], { stdio: "inherit", shell: true })`.
2. Add `tzdata` to `[project] dependencies` in `apps/api/pyproject.toml`.
3. On a Windows development machine run `pnpm setup:api`, then verify `python -m app --help` and that `pnpm dev` starts both child processes.

## Dependencies and boundary

- Dependencies: none (the m2 platform skeleton is already in place).
- Non-goals: do not turn `pnpm dev` into a process manager or adopt `concurrently`; do not fix the Windows entry checks of CI-only scripts such as `flow-new-issue.mjs` (separate issue); do not cover local MySQL installation.

## Verification

```sh
pnpm dev
```

- On Windows 11 + Node 22: within about 15 seconds `http://127.0.0.1:8787/api/health` returns `{"ok":true,…}` and `http://localhost:5173` returns 200; Ctrl+C exits both child processes.

```sh
pnpm setup:api; pnpm data:import:sessions
```

- On a fresh `apps/api/.venv` (no manual `pip install tzdata`) the command no longer fails with `ZoneInfoNotFoundError: 'No time zone found with key Asia/Shanghai'` and prints its `{"status": …}` JSON.

## Acceptance

- On Windows a single `pnpm dev` brings up API(8787) and Web(5173) with exit code 0 and no `spawn EINVAL`.
- `import app.main` succeeds in a fresh venv with no system tz database required.
- POSIX (CI) behavior is unchanged: `pnpm dev`, `pnpm test:api`, and related commands produce the same results as before the change.

## Gates and CI

- `pnpm test:gates` (covering `scripts/gates.spec.mjs`; this issue does not touch gate scripts and they must stay green).
- `pnpm lint:api` / `pnpm typecheck:api`: dependency resolution must pass after the `pyproject.toml` change.
- On CI (Ubuntu) the `pnpm dev` path is unaffected by the `shell: true` branch; the existing ≥80% coverage floor is not relaxed.

## Non-goals

- No unification of cross-platform spawn strategy across all scripts (such as a global `shell: true` audit).
- No Windows compatibility for the `import.meta.url` entry checks in `flow-new-issue.mjs` or other scripts (to be filed separately).
- No local MySQL or production deployment changes.
