# Agent Note: Session Browser Performance Budgets

Status: implemented

English | [中文](2026-10-26-session-performance.md)

## Problem

Vue Flow is already route-lazy and Session list/detail requests are independent, but the guard only proved that lazy boundary existed. It did not bound entry, gzip, or vendor bytes. The largest local Agent tree also lacked a repeatable CI scenario. The list and overview are separate scroll containers, so switching Sessions or using browser History reset long-tree context to the top.

## Decision

`scripts/verify-bundle.mjs` turns design budgets into hard gates: the synchronous entry stays within 250KB raw and 90KB gzip, each manual vendor chunk stays within 400KB raw, and Vue Flow remains outside the first-screen synchronous closure. `tests/e2e/m3-session-browser.test.mjs` records card readiness, interaction latency, scroll frame pacing, long tasks, request ordering, and lazy-loading evidence against real FastAPI, SQLite, Vite, and Chrome. CI uses the development-only `/agent-tree-demo?variant=stress` 61-Agent synthetic tree, while `pnpm performance:report --local` imports and replays local sessions and selects the largest real tree. Both report modes include browser, phase, and source context without trace text or local paths.

The Session page keeps separate list and overview offsets per Session in memory through `SessionScrollMemory`. Selection and History navigation save the departing Session and restore the target after DOM and overview data are ready. Reload intentionally resets positions; these temporary UI offsets never enter the URL or cross-tab storage.

## Alternatives considered

- Check Vue Flow lazy loading only: entry or vendor growth would remain invisible.
- Depend on the ignored local 61-Agent trace in CI: results would not be reproducible.
- Put scroll offsets in the URL: Session deep links already carry Agent/evidence, and adding viewport state expands the canonical contract.

## Consequences

CI blocks meaningful bundle and runtime regressions with a deterministic synthetic tree. Runtime thresholds are shared by E2E and reports: cards/largest-tree readiness 2500ms, 61-Agent expansion 350ms, interaction 200ms, long tasks 200ms, and average scroll frame 34ms. The local maximum-tree baseline is approximately 698ms, 34ms, 13ms, 0ms, and 16.72ms respectively, leaving room for runner variation while still catching substantial regressions. Raw phase measurements remain in the report, while absolute large-local-tree TTFB stays observational rather than a machine-dependent gate. Local reports use the project Python standard library rather than a system `sqlite3` executable. Scroll state is scoped to the current SPA and tab; reload reset behavior is explicit and testable. Documentation-budget increases register the new performance commands, threshold rationale, and current-state architecture facts after relocation and compression were exhausted.
