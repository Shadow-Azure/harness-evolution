# Agent Note: Run detail consumes backend-owned six-step state

Status: implemented

English | [中文](2026-10-27-run-detail-ui.md)

## Problem

The run detail must show target input, workspace, blocked/retry/eval context, six-step navigation, and the selected step output together. m5-06 already made the backend the authority for six-step `status/clickable`; recomputing them from `progress.unit` or probing unreached endpoints would create a second state rule and needless `STEP_NOT_READY` requests. The run list alone lacks workspace and the complete step array, while each step response describes only itself.

## Decision

- `GET /api/evolution/runs/{run_id}` returns `RunDetail`: it reuses the run-card statistics, progress, terminal summary, and error summary, and adds workspace, blocked/retry/eval fields, `lastEventSeq`, and six `steps`.
- The detail service calls the same `step_states` cursor state machine as the six step endpoints and emits `status/clickable` unchanged. The iteration step gets its "turn x/y" detail only while active; the frontend never derives state from progress.
- The detail page first requests `RunDetail` plus the default reached step. It selects the first active step, otherwise the last done step. A `?step=` query takes effect only when the backend marks it clickable. Selecting a reached node updates the query and requests only that step; pending nodes stay disabled and issue no request.
- When a run fails or is interrupted before the first step completes, all six nodes are unreadable. The page says the step has not been reached and the run ended before step 1 instead of treating the disabled query as permanent loading.
- Target input and workspace use the same backend snapshot: branch, base ref/commit, repository, subdirectory, workspace/repo paths, push/eval state, and blocked error all come from the run record. Loading, error retry, and non-retryable `RUN_NOT_FOUND` states stay explicit.
- Six components render the structured 05 §3.6 payload: filter rows deduplicate repeated probe IDs; clusters and iteration cards reuse one six-column source-problem table whose report IDs open attribution and source-issue IDs open descriptions; attribution analysis uses Markdown with raw HTML disabled; severity preserves backend order.
- Iteration cards map the closed turn-status set together with push/eval failure substatuses to patch, push, eval, deciding, accepted, rejected, and failure copy, and use the run-level blocked stage to identify patch/push/eval blockage; turn status excludes blocked, and deciding is not terminal. Acceptance rather than score direction determines the outcome copy. The final evaluation shows final push status and time, and the workspace branch name is copyable.
- `lastEventSeq` is currently 0; m5-08 owns event pagination/SSE. m5-11 owns the blocked retry action. The detail renders current recovery context without a manual advance action.

## Alternatives considered

- Recomputing six-step state from frontend `progress.unit`: this conflicts with the backend authority established by m5-06 and duplicates boundary, blocked, and terminal rules; rejected.
- Requesting all six steps and using 404 to discover pending nodes: this requests unreached steps by design and amplifies failure paths; rejected.
- Building detail from the run list: the list contract has no workspace, complete steps, or retry/eval context, and extending it would still change the API; rejected.
- Keeping workspace only in frontend local state: refresh and deep links would lose backend facts and blocked recovery could not reuse them; rejected.

## Consequences

- The run-detail UI and visual/E2E suites depend on one detail shell plus one step request; refresh, deep links, and pending-node disabling share one contract.
- `GET /runs/{rid}` and the step endpoints both depend on `step_states`; future cursor changes must cover detail and six-step tests together.
- Turn/push/eval and blocked-stage values use shared contract enums. A new state must update the API Literal, generated contracts, frontend state tests, and prototype copy together.
- m5-08 can fill real `lastEventSeq` in the same detail contract, and m5-11 can wire recovery into the blocked banner without frontend state inference.
- Fixtures write session, bad-case, probe, and association rows for every cluster and keep run/iteration/workspace push and eval states consistent. Component/E2E tests cover completed, running/evaluating, blocked, invalid cluster links, and the 390px layout.
