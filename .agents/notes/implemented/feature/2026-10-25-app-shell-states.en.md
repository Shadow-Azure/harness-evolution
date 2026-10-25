# Agent Note: M1 shell and demo state

Status: implemented

English | [中文](2026-10-25-app-shell-states.md)

## Problem

M1 has no domain data, but authenticated users still need stable product destinations, consistent state feedback, and a safe global exception outlet. Per-page loading, empty, and error implementations would duplicate behavior; fabricating sessions in the CLI would also create cleanup debt when M2 introduces real data.

## Decision

- The authenticated shell always exposes Sessions, Errors, and Evolution. Errors only explains that problem ownership arrives in a later milestone and never renders fake problem rows.
- Pages share `LoadingSkeleton`, `EmptyState`, and `ErrorState`; health renders a skeleton inside the shell while loading and a retryable error state on failure, while 404 uses the terminal copy “does not exist or was deleted.” Query and mutation 409 `RUN_BUSY` conflicts use a styled `ElMessage` and leave the current page in place; uncaught Vue errors are logged and presented through one generic `ElMessage` while the mounted shell remains available.
- The health `phase` is the sole demo marker: only `demo` shows the demo-data badge; `scaffold` and `live` do not.
- `fixtures/m1-shell.json` is a strict, closed seed manifest for M1. `python -m app.cli seed` runs migrations and reuses idempotent administrator seeding, rejects production/live targets, and creates no sessions, problems, probes, runs, or other domain rows.
- Real-browser E2E runs against the API and Vite processes and covers authenticated navigation, empty states, the Errors placeholder, the demo badge, clean console output, and narrow layout.

## Alternatives considered

- Seed four demo sessions so the empty state looks richer: this blurs M2-01 fixture ownership and hides the real integration gap; rejected.
- Let each page implement its own state UI: fewer shared components initially, but split error copy, retry, and accessibility semantics over time; rejected.
- Add a runtime stub provider for demo data: this creates a second data path beside real tables; rejected.

## Consequences

- M1's demo entry points are a real shell and CLI while domain areas remain honest empty states.
- M2-01 owns the full fixture schema and session data; it should extend the seed manifest/action rather than bypass the CLI.
- Session-scoped problem details remain for a later milestone; the top-level Errors entry only establishes navigation and boundary copy in M1.
