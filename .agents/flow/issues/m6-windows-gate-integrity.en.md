# Windows gate integrity: real main guards and web-style compat

English | [中文](m6-windows-gate-integrity.md)

```yaml flow
kind: issue
id: m6-11
milestone: m6
depends:
  - m6-05
priority: P2
status: backlog
scope:
  - scripts/**
  - .agents/flow/**
  - .agents/notes/**
  - docs/**
adr: []
github:
  number: 163
  url: https://github.com/Shadow-Azure/harness-evolution/issues/163
```

## Background

The CLI entry guard in 22 gate/utility scripts under `scripts/` reads ``if (import.meta.url === `file://${process.argv[1]}`)``. The comparison is POSIX-only: `import.meta.url` is a three-slash forward-slash `file:///D:/...` URL, while the template literal yields a two-slash backslash path (`file://D:\...\x.mjs`), so on Windows the comparison is always false — running `node scripts/xxx.mjs` directly skips the main block silently and exits 0. As a result, `pnpm verify:web-style`, `pnpm verify:docs`, `pnpm verify:flow` and friends are fake-green on Windows (no-op exit 0) and "I ran the gates locally" proves nothing; CI runs entirely on `runs-on: ubuntu-latest` where the guard holds, so CI results are unaffected, but the local defense line for Windows developers is effectively absent. m6-05 (GitHub #118) recorded this defect and promised "a separate issue" in its non-goals, which never landed. One more independent layer: `scripts/verify-web-style.mjs:22-28` still cannot run on Windows even with the entry fixed — the main block builds file URLs via `new URL(path, sourceRoot)`, while `readdir(…, { recursive: true, withFileTypes: true })` on Windows reports an absolute backslash `entry.parentPath`; the joined string starts with `D:`, the URL parser treats it as the `d:` scheme, and it throws `TypeError [ERR_INVALID_URL_SCHEME]`.

## Goals

- Unify the 22 entry guards into the cross-platform form ``import.meta.url === pathToFileURL(process.argv[1]).href`` (or extract a shared `isMain()` helper and swap it in everywhere), so executing a script directly on Windows really enters the main block.
- Make `pnpm verify:web-style` actually run to a result on Windows: file paths go through `pathToFileURL(path.join(entry.parentPath, entry.name))` instead of feeding backslash absolute paths into `new URL`.
- Restore the local defense line on Windows: the `pnpm verify:*` family produces real, CI-isomorphic results on the developer machine, and the fake-green path disappears.

## Design authority

- [plans/2026-10-29-pr160-review.md §6-1/§6-2](../../../plans/2026-10-29-pr160-review.md): reach statistics of the 22 guards plus the Windows measured evidence (no-op exit 0 and the `ERR_INVALID_URL_SCHEME` stack).
- `scripts/contract.mjs:259` and `scripts/performance-report.mjs:73`: existing in-repo `pathToFileURL(...).href` guard templates.
- [m6-windows-dev-entry.en.md](m6-windows-dev-entry.en.md): where m6-05 (GitHub #118) promised "a separate issue" in its non-goals.

## Implementation

- Unify the 22 guards into ``import.meta.url === pathToFileURL(process.argv[1]).href`` (following `scripts/contract.mjs:259`, optionally with a `process.argv[1] &&` prefix); if repetition costs too much, extract a shared `isMain()` helper and swap it in per script.
- One-line fix at `scripts/verify-web-style.mjs:27-28`: build the read path and URL with `pathToFileURL(path.join(entry.parentPath, entry.name))`.
- Add a Windows smoke assertion for verify-web-style to the `pnpm test:gates` self-tests: inject a sample carrying a literal color and assert the gate goes red, guarding against the "entry reachable but gate body never ran" regression.
- Dispose of `.tmp/run-gate.mjs`: once the guards are fixed it loses its reason to exist; promote it to a proper `scripts/` tool or delete it as needed.

## Implementation steps

1. Settle the guard form (inline `pathToFileURL` or a shared `isMain()`), replace the 22 sites one by one, changing only "is the main block reachable" and never any verdict logic.
2. Fix the `entry.parentPath` URL joining in `verify-web-style.mjs` (one line).
3. Add the Windows guard-reachability assertions and the web-style smoke sample to `scripts/gates.spec.mjs`.
4. Measure each item under Verification on a Windows dev machine, then dispose of `.tmp/run-gate.mjs`.

## Dependencies and boundary

- Depends on: m6-05 (the Windows dev entry already works; this issue honors its "separate issue" promise).
- Boundary: only the entry guards and Windows path compatibility under `scripts/`, the matching self-tests, and flow-doc sync; no gate's verdict semantics and no CI workflow change.

## Verification

```sh
pnpm verify:web-style
```

- Real output on Windows (`verify-web-style: Vue components use token colors only`) instead of a silent no-op; a temporary sample with an injected literal color goes red.

```sh
pnpm verify:flow
pnpm verify:docs
```

- Both produce real output and pass on Windows (silently exiting 0 before the fix).

```sh
pnpm test:gates
```

- All green, including the new guard-reachability assertions.

## Acceptance

- On Windows, `node scripts/verify-web-style.mjs` (without any runner) really executes and produces CI-isomorphic output.
- All 22 guards are reachable on Windows; POSIX/CI behavior stays as before.
- `pnpm test:gates` is all green; `.tmp/run-gate.mjs` is promoted or deleted, and the repo no longer needs a Windows-only runner for the gates.

## Gates and CI

- `pnpm test:gates` (guard changes must keep `scripts/gates.spec.mjs` in sync).
- `pnpm verify:flow` / `pnpm lint:docs` / `pnpm verify:docs`.
- CI (ubuntu) is unaffected: both guard forms are equivalent on POSIX and verdict logic is untouched.

## Non-goals

- No gate's verdict logic changes (only "is the main block reachable" and how file paths become URLs).
- No Windows CI lane for e2e; "Windows local e2e smoke" is registered in an Agent Note as a known verification method for that environment.
- The fixture fake-domain catalog 422 and per-target fault isolation stay out (archived as backlog in plans/2026-10-29-pr160-review.md §6-7).
