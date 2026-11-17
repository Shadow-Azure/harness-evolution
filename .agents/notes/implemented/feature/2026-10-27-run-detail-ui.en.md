# Agent Note: Run detail consumes backend-owned seven-step state

Status: implemented

English | [中文](2026-10-27-run-detail-ui.md)

## Problem

The run detail must show target input, workspace, blocked/retry/eval context, seven-step navigation, and the selected step output together. m10-04 already made the backend the authority for seven-step `status/clickable`; recomputing them from `progress.unit` or probing unreached endpoints would create a second state rule and needless `STEP_NOT_READY` requests. The run list alone lacks workspace and the complete step array, while each step response describes only itself. Historical six-step runs must share the same interface, so the page cannot keep a second step schema.

## Decision

- `GET /api/workspaces/{wid}/evolution/runs/{run_id}` returns `RunDetail`: it reuses the run-card statistics, progress, terminal summary, and error summary, and adds workspace, blocked/retry/eval fields, `lastEventSeq`, and seven `steps`. The step keys are fixed at `range / sessions / potential / attribution / clusters / iteration / final`.
- The detail service calls the same `step_states` cursor state machine as the seven step endpoints and emits `status/clickable` unchanged. The iteration step gets its "turn x/y" detail only while active; the frontend never derives state from progress. The backend projects a V1 run from its probe rows into the same seven-step DTO, so the frontend does not branch on data origin.
- The detail page requests only `RunDetail` plus the default reached step. It selects the first active step, otherwise the last done step. A `?step=` query takes effect only when the backend marks it clickable. Selecting a reached node updates the query and requests only that step; pending nodes stay disabled and issue no request. When a run fails or is interrupted before step 1 completes, all seven nodes say the step has not been reached.
- Step 2 uses server paging at 4 rows per page and Step 3 at 5; paging re-requests only the current step endpoint's `page` and never recomputes the condition. Step 4 renders every attribution row returned by its step endpoint and reads the server `summary` for `potential / reused / fresh / nonTarget` instead of counting rows in the browser.
- Step 4 renders `category=null` as "非该对象问题" and labels `source` as cached or fresh. Those rows are visible in Step 4, but the backend clusters only attributed candidates, so non_target never appears in a Step 5 cluster.
- Step 5 preserves the backend severity-descending order and expands the first cluster by default. A `?cluster=` deep link expands and highlights an existing cluster; when the target is missing the page drops the parameter and says so instead of inventing a position. Steps 6 and 7 keep the existing turn and final-evaluation cards.
- Target input and workspace use the same backend snapshot: branch, base ref/commit, repository, subdirectory, workspace/repo paths, push/eval state, and blocked error all come from the run record. Loading, error retry, and non-retryable `RUN_NOT_FOUND` states stay explicit.
- The blocked banner covers patch, push, eval, and attribution. It shows the stage, sanitized error, automatic retry count, next automatic retry time, and a manual retry button. An accepted retry is debounced and restored on its own, and acceptance is never presented as success. The final evaluation shows final push status and time, and the workspace branch name is copyable.
- The execution log uses REST pages as the source of truth, seeds the SSE cursor from `lastEventSeq`, and merges `run.event` frames by seq without duplicates. Events with `stepIndex` jump to that step, events with `clusterId` jump to and highlight that cluster, and error details stay collapsed and redacted until requested. Resetting a run clears both the log and the active run so stale events cannot leak across runs.
- The event log, blocked retry, and step data reuse the existing endpoints; no second step schema is introduced. For a cluster-only run the backend hides iteration and final with 404 and the frontend never synthesizes those nodes.

## Alternatives considered

- Recomputing seven-step state from frontend `progress.unit`: this conflicts with the backend authority established by m10-04 and duplicates boundary, blocked, and terminal rules; rejected.
- Requesting all seven steps and using 404 to discover pending nodes: this requests unreached steps by design and amplifies failure paths; rejected.
- Building detail from the run list: the list contract has no workspace, complete steps, or retry/eval context, and extending it would still change the API; rejected.
- Adding frontend-only paging to Step 4: the contract has no paging fields, so browser paging would drift from the server row order and statistics; the page shows the attribution rows returned in one step response and leaves paging to API evolution.
- Keeping workspace, policy, or cache only in frontend local state: refresh and deep links would lose backend facts and blocked recovery could not reuse them; rejected.
- Re-sorting clusters in the browser: the backend persists rank and severity, and frontend reordering would diverge from deep links, iteration turns, and final-evaluation references; rejected.

## Consequences

- The run-detail UI and visual/E2E suites depend on one detail shell plus one step request; refresh, deep links, paging, and pending-node disabling share one contract.
- `GET /runs/{rid}` and the step endpoints both depend on `step_states`; future cursor changes must cover detail and seven-step tests together.
- The blocked stage uses the shared contract enum (patch/push/eval/attribution). A new state must update the API Literal, generated contracts, frontend state tests, and prototype copy together.
- Event-to-step linkage relies on the optional `stepIndex` and `clusterId` coordinates. New event types reuse the existing jump rules without changing the page schema.
- The V2 and legacy run E2E fixtures both write the candidates, probes, clusters, turns, and events the seven-step DTO needs. E2E covers Session/potential paging, cached/fresh/non_target, cluster severity order and first-cluster expansion, blocked attribution retry facts, no request for unreached steps, and jumps from events to step, cluster, and error detail.
