# Agent Note: V2 cross-stack acceptance evidence layers

Status: implemented

English | [中文](2026-11-17-v2-cross-stack-acceptance.md)

## Problem

Every V2 module has its own green tests, but the user's seven requirements cross identity, workspaces, ingest, overview, attribution, and pages. Module-level green does not prove the real chain "login → workspace switch → ingest → overview → wizard → run → error detail → lane DAG": permission matrices, cross-workspace invisibility, quota and idempotency, one potential count in three places, cache reuse, and migration/replay/SSE can all break at module boundaries.

## Decision

- Add the API acceptance suite `apps/api/tests/m11-05-v2-cross-stack/` with one multi-workspace fixture split into three groups: security matrix (invisible workspace 404, member/viewer writes 403, space admins cannot grant space admins, cross-workspace credential 403), potential and cache consistency (wizard preview, run candidates, and target overview report the same count; a second attribution run reuses the cache; non-target results stay out of clusters), and migration/replay/SSE (SQLite upgrades to head, Skill/Agent/knowledge triggers and derived parent-child relations, idempotent replay, one-shot SSE ticket).
- Add one real-browser E2E, `tests/e2e/m11-05-v2-cross-stack.test.mjs`: temporary SQLite plus the demo corpus, real login form, workspace switch, credentialed ingest (including idempotency and quota 409), bad-case and target overview, latest-ten Session list with Enter search, multi-attribution error detail, four-step wizard, cluster-only run, seven-step run detail, and lane DAG/structure-tree switching; key steps also assert API facts.
- Keep smoke screenshots and the smoke report out of the repository as temporary PR release assets; the PR description carries only desensitized scenario conclusions and asset links.
- The smoke found that `ClusterPreview` reused the run-list cache and never polled, so a completed cluster-only run stayed on "preparing". Read `useEvolutionRunDetail` with `runDetailRefetchInterval` instead; active runs refresh every 15 seconds and show the terminal state automatically.

## Alternatives considered

- Extend every existing module test: coverage stays inside modules, cannot prove cross-stack order or a shared fixture, and scatters one scenario across directories.
- Snapshots or mocks only: cannot verify real HTTP, real SQLite, a real browser, and real run progress, and conflicts with "do not replace API assertions with manual screenshots".
- Poll the global run list to rescue the cluster preview: it pulls every historical run, costs more than reading one run detail by id, and the detail endpoint already has stable polling semantics and unit tests.
- Reload the page to bypass "preparing": the test goes green while users still see a stuck page, leaving the defect in the product.

## Consequences

- The E2E adds about 25 seconds and the API suite about 100 cases; the MySQL case keeps the existing `mysql` marker, skips when no service exists, and runs through `test:db:mysql` in CI.
- The cluster preview reads one detail every 15 seconds while a run is active and stops at a terminal state; this fills a page-cache gap without changing the run state machine.
- Acceptance reports and screenshots stay out of the repository, so long-term evidence depends on release assets in the PR; if those assets are deleted, only the PR description and review document remain.
- Fixtures stay synthetic; real session shapes are covered through replay cases without introducing raw prompts or document bodies.
