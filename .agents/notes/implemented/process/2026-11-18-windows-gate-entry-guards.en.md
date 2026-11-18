# Agent Note: cross-platform entry guards for local Windows gates

Status: implemented

English | [中文](2026-11-18-windows-gate-entry-guards.md)

## Problem

On Windows developer machines, the CLI entry guards under `scripts/` compare `import.meta.url` directly with `` `file://${process.argv[1]}` ``. Windows reports `import.meta.url` as a three-slash forward-slash `file:///D:/...` URL, while the template literal yields a two-slash backslash path (`file://D:\...`), so the comparison is always false: running `node scripts/verify-flow.mjs` and friends skips the main block silently and exits 0, making `pnpm verify:*` fake-green. A second independent layer: `verify-web-style.mjs` reads the `entry.parentPath` reported by `readdir` through `new URL(path, sourceRoot)`; a Windows backslash absolute path starts with `D:`, which the URL parser treats as the `d:` scheme and rejects with `ERR_INVALID_URL_SCHEME`. CI runs entirely on Ubuntu where the guard holds, so CI never exposes this local-defense gap.

## Decision

- Add `isMain(moduleUrl, entryPath = process.argv[1])` in `scripts/is-main.mjs`, comparing `pathToFileURL(realpathSync(entryPath)).href` with `import.meta.url` (`realpath` also removes path differences when a script is reached through a symlink); all 24 script entries use it (the 22 legacy guards plus the two already-safe guards in `contract.mjs` and `performance-report.mjs`).
- `verify-web-style.mjs` keeps `import.meta.url` as the directory anchor; each file path is built with `path.join(entry.parentPath, entry.name)` and read via `pathToFileURL(...)` instead of joining a Windows absolute path into a relative URL.
- `gates.spec.mjs` gains three regressions: `isMain` equivalence for absolute, relative, and spaced paths; a static audit of every script (no legacy template literal, and any entry guard must import the helper); and a real CLI run from a temporary directory with an injected literal-color Vue sample, asserting both the success output and the red exit. The last two guard against "entry reachable but gate body never ran".
- `.tmp/run-gate.mjs` stays out of the repository: it was only a local Windows runner that bypassed the old guard, and the repository depends on no platform-specific runner.
- Gate verdict logic is untouched and `.github/workflows` is unchanged.

## Alternatives considered

- Inline `pathToFileURL` in every script: one fewer shared file, but 24 equivalent comparisons drift easily and regression tests could only match strings one by one; no.
- Compare paths via `fileURLToPath` + `path.resolve`: semantically equivalent, but it diverges from the repository's existing `pathToFileURL(...).href` template and would need URL decoding; no.
- Add a Windows CI lane: explicitly excluded by m12-05's non-goals, and the repository already keeps "Windows local e2e smoke" as a manual verification mode; no.

## Consequences

- On Windows, gates run directly or through `pnpm verify:*` now really enter their main block, so silent no-op fake-green disappears; POSIX and CI behavior are unchanged.
- Guard correctness relies on Node's `pathToFileURL` semantics. The self-tests cover entry reachability, the static audit, and a subprocess smoke on POSIX; Windows runtime verification remains with a Windows developer machine per the issue's verification section because there is no Windows CI lane.
- New gate scripts with a CLI entry must import `isMain` and use `isMain(import.meta.url)`; the static audit blocks the legacy form.
- Windows local e2e smoke remains a manual verification mode outside CI coverage.
