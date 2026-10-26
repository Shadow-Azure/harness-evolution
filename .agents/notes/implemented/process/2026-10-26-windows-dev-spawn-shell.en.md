# Agent Note: spawn shell for the Windows dev entry and declared tzdata

Status: implemented

English | [中文](2026-10-26-windows-dev-spawn-shell.md)

## Problem

On Windows with Node ≥18.20/20.12/22, `scripts/dev.mjs` spawns `pnpm.cmd` without `shell`, which trips Node's CVE-2024-27980 hardening for `.cmd`/`.bat` targets; `pnpm dev` throws `spawn EINVAL`, and the m2 acceptance command "one command starts frontend and backend" is unusable on Windows. A second independent defect on the same machine: `ZoneInfo("Asia/Shanghai")` in `app/utils/time.py` depends on a system tz database that Windows Python does not ship, so any command whose import chain touches the timezone module (including the session import pipeline) crashes outright. Both problems only surface on local Windows machines; CI (Ubuntu) can never detect them.

## Decision

- `dev.mjs` adds `shell: true` to spawn only when `process.platform === "win32"`; the POSIX branch stays as-is, and signal forwarding plus exit-code logic are untouched. The shell exists solely to launch the pnpm shim.
- `tzdata` joins the `apps/api` runtime dependencies with an upper-bounded range per repository convention; on Linux/macOS it is merely a fallback zoneinfo source and changes no behavior.
- Similar Windows entry defects in other scripts (such as the backslash `import.meta.url` comparison in `flow-new-issue.mjs` that makes the CLI exit silently) are out of scope here and will be filed separately.

## Alternatives considered

- `shell: true` everywhere: on POSIX an extra shell layer only widens the quoting and signal-forwarding risk surface for zero benefit; no — branch by platform.
- Resolving the full `pnpm.cmd` path or prefixing `cmd /c`: equivalent to `shell: true` but more fragile, and Node's own fix guidance recommends a shell or switching to `.exe`; no.
- Documenting a manual `pip install tzdata` step for Windows developers: shifts a platform difference onto people, and every new machine would trip again; no — declared dependencies are the only reliable place.
- Replacing `dev.mjs` with a process-manager dependency such as `concurrently`: not worth a third-party dependency for two child processes when the existing zero-dependency design is one spawn option short; no.

## Consequences

- `pnpm dev` behavior is aligned across Windows and POSIX, but on Windows Ctrl+C is relayed through a shell, so in extreme cases child-tree termination depends on cmd's default behavior; if zombie processes ever appear, suspect this layer first.
- With `tzdata` as a cross-platform dependency, zoneinfo data upgrades track the PyPI release instead of OS tzdata updates; verification of timezone rule changes should watch that package's version.
- Scripts such as `flow-new-issue.mjs` remain unusable on Windows; maintainers must temporarily reach for module calls to operate the flow tree on that platform until a sibling issue lands.
