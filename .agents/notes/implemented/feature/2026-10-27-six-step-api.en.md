# Agent Note: Six read-only step endpoints with backend-owned status semantics

Status: implemented

English | [中文](2026-10-27-six-step-api.md)

## Problem

m5-06 must realize the six read-only endpoints of 05 §3.6 without copying design facts: the run-detail page renders a different body per step, but the state judgment (done/active/pending, clickable, 404 for unreached steps) must have exactly one authority. Meanwhile the execution engine does not exist yet — the only write path is the m5-01 placeholder prepare — so the read endpoints must also define clear behavior for runs that never really advanced.

## Decision

- Readiness comes solely from the m5-01 unit-cursor state machine: `EvolutionStageService` derives each step status through `step_states` and emits `clickable = status != "pending"` server-side (R4); the six endpoints share one `build_step_payload(run, clusters, key)` that assembles each DTO by key and copies no state logic.
- Score columns are read, never recomputed: `confidence/impact/severity/rank` come straight from `probe_clusters` columns (07 §5.10 "the API reads these columns and no longer computes placeholders"), `probeCount/reportCount` are read-time join counts, and ordering follows the stored severity descending with unranked clusters last.
- 404 semantics: an unknown run returns `RUN_NOT_FOUND`; a pending step returns `STEP_NOT_READY` (details carry the key); the `input` step of a `preparing` run returns the preparation state — `status=active` with the condition snapshot, zeroed hits, and empty rows — not a 404 (05 §3.6).
- An unfinished final uses `null` instead of zero values: while `evolution_finals` has no row, `StepFinalPayload.verdict/bestVersion/bestScore/initScore` are `null` and `metrics` is `[]`, while `changes` still lists accepted rounds; "0 points" carries business meaning, and a zero would disguise "no result yet" as "final failed" (05 §3.6).
- blocked invents no second cursor: a blocked run keeps done steps readable, its active step (e.g. iteration) stays readable with the "turn x/y" detail, and later steps 404; a cluster_only run answers only `input`/`clusters` whether it is still running or terminal — `attribution/severity/iteration/final` are hidden by the readiness entry point (the `mode` argument of `ensure_step_readable`) per 05 §4.12, while `step_states` stays a pure cursor state machine; clusters render null confidence/severity.
- Step 0 `hits` count the probes already clustered for this run instead of re-running the condition query (05 §3.6, 07 §5.10): the read path only reads persisted facts, stays auditable, and never re-runs filtering; once prepare is real, add a "N hits / M clustered" reconciliation test in a later slice, not in this PR.
- Six fixture groups shaped after 05 §3.6.1 plus six response snapshots (and the `step-final-active` variant for the active final) live in `apps/api/tests/m5-06-six-step-api/` (the issue's verification directory), not in the root `fixtures/` — that directory is the seed corpus home.
- Fact sync: the real prepare orchestration (workspace/ref validation, filtering, clustering, cursor advancement) and the `ENGINE_INVALID` engine-registry check are owned by engine slice m5-09 (inside the m5-09–m5-11 range), not this slice; the m5-05 note and the placeholder handler now say so.

## Alternatives considered

- A single `GET /steps/{key}` dynamic route: 05 §3.6 splits the six steps into six independent endpoints, and a dynamic key would defer the response-shape discrimination to runtime while OpenAPI could not shape each endpoint; rejected.
- Recomputing placeholder confidence/severity in the stage service for absent values: it would drift into a second source of truth and race the write path; rejected.
- Putting the cluster_only hiding rule inside `step_states`: mode would leak into the cursor state machine R4 wants pure, and each of the four steps would have to remember it; rejected — the readiness entry point guards 05 §4.12 instead, keeping the state machine mode-free.
- Keeping zero values for the active final and declaring "zero means no result yet" as contract semantics: "0 points" is shaped exactly like "final failed", so m5-07 could only tell them apart by status; rejected.

## Consequences

- The run-detail UI (m5-07) consumes status/clickable and each payload directly; the frontend stops deriving step state, and `step=` deep links become a lookup.
- The six §3.6.1 snapshots plus the active-final variant are the comparison baseline for the execution engine (m5-09–m5-11): once the engine writes rows, the read shapes must match the snapshots, and any drift counts as the engine breaking the read contract.
- The zeroed hits of `input` during preparing are a defined empty state, not an error; an active final with no terminal row keeps its four verdict fields `null`, so m5-07 must render by status and never read null as failure; the iteration detail appears only while active, and done steps keep `detail` at null.
- The "always 404" rule for cluster_only is now enforced by the readiness guard instead of relying on the future premise that the engine ends the run terminal; engine slices need no mode special case when they wire prepare.
- Run-level readiness depends on `list_clusters` counting M; if clusters ever become soft-deleted or shared across runs, the `total_units` basis must be rechecked.
