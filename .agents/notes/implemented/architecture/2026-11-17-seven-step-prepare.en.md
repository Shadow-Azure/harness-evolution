# Agent Note: Seven-step prepare, cluster input, and legacy run adaptation

Status: implemented

English | [中文](2026-11-17-seven-step-prepare.md)

## Problem

The V2 input chain is "workspace bad cases → Session association → potential bad cases → object attribution → clustering". The V1 prepare pipeline clustered analyzed probes directly, without version-exact Session association, potential selection, or cache reuse; the read side still spoke six keys (`input/clusters/attribution/severity`) and treated probes as the problem itself. Changing only prepare would leave new runs writing a seven-step cursor while pages interpret six steps; deleting V1 data would make historical runs unreadable. Retried prepare, blocked recovery, and `blocked(attribution)` must stay idempotent or they duplicate candidates and engine calls.

## Decision

- The state machine has seven steps: `range / sessions / potential / attribution / clusters / iteration / final`, with thresholds `1,2,3,4,5,5+M,6+M` and `total = 5 + M + 1`. Prepared is always unit 5; `cluster_only` becomes `completed` at unit 5 and hides `iteration/final` with 404.
- Prepare advances by stage: validate → `sessions` (shared matcher `associated_sessions`) → `potential` (same matcher `potential_cases`) → batch-upsert candidates → `attribution` (`AttributionRunner`) → cluster only attributed candidates and persist confidence/severity/rank → workspace and rounds → `mark_prepared(5)`. Each stage commits its writes before moving the cursor, so retries resume from the cursor.
- Candidate uniqueness is `(run_id, bad_case_id)` with a single-transaction batch upsert; repeated prepare adds no candidates. The attribution stage rebuilds included rows from the candidate table, and the runner skips cases with a candidate `probe_id`, so `blocked(attribution)` re-entry only fills the gap.
- Cluster input is exactly `evolution_run_candidates.included=true` joined to `probe_reports.conclusion='attributed'`; `non_target` rows keep their attribution and candidate row but never enter a cluster. Cluster confidence is category-based (`error 0.82 / prompt 0.74 / model 0.66`), severity is `min(10, confidence x impact x reportWeight)`, and rank is severity-descending.
- The read side has one `build_step_payload`: range reads the run snapshot, sessions/potential read candidates, attribution reads candidates plus probe links, clusters read the cluster snapshot and members, iteration/final read rounds/final. Unreached steps return `STEP_NOT_READY`; cluster_only hides only iteration/final.
- Historical V1 runs are identified by `attribution_engine='legacy-probe-import'` and are **not rewritten**: at read time 0/1 stay as-is, 2–4 map to prepared unit 5, and >=5 shift by one. V1 probes/clusters/rounds are mapped by the same builder's compatibility branch; sessions/potential rows are synthesized from probes and source cases, and a missing comparable anchor stays `orderState=unknown` rather than inventing order.
- Seven-step events add `sessions_linked / potential_computed / attribution_created / attribution_reused`; attribution events are batched at 20 rows to protect the event table and SSE.

## Alternatives considered

- **Keep six-step reads and change only prepare**: cursor semantics and page state would drift, and sessions/potential could not be expressed; rejected, read and write switch together.
- **Migrate historical runs by rewriting cursors**: this rewrites immutable history, needs a backfill rollback plan, and cannot truly reconstruct V2 sessions/potential rows; rejected, use a read-only projection.
- **Split each prepare stage into its own job**: no independent rerun UI exists yet, and it adds new scheduling and idempotency surface; rejected, keep one prepare job that writes before advancing.
- **Keep clustering every probe**: non_target and policy-excluded rows would pollute clusters and severity; rejected, the repository projects only attributed candidates.
- **Compute potentialCount per sessions page row**: this repeats the full potential query for each page; m10-02 already removed that field from preview, so the read side uses the candidate snapshot's included count instead.
- **Create rounds for cluster_only**: this would fabricate iterations that never run; rejected, unit 5 is terminal.
- **Recompute every candidate on attribution retry**: this repeats engine calls and overwrites completed conclusions; rejected, the candidate probe pointer marks completion.

## Consequences

- The seven-step schema is the only schema; the run detail, RunCard, and event log move to the seven keys in the same PR, and the old six-step DTOs are no longer published.
- Historical sessions/potential rows are synthesized: `title` may be empty, `orderState` may be `unknown`, and trigger points may be missing; they explain history and must not be presented as new exact-match evidence.
- `prepare` remains a single job; clustering, workspace, and rounds run sequentially inside it, and recovery relies on the cursor and candidate/probe pointers rather than stage-level job retries.
- `EvolutionRunStats` becomes `sessions/versionUnresolvedSessions/badCases/potential/attributed/reused/clusters/byCategory`; historical runs derive it from the old `probes/usedProbes/byAttributeType` counts.
- `rule-v1` is still a placeholder, and cluster descriptions and severity are placeholder semantics; real clustering and engine upgrades stay in M12, while this Note fixes the input boundary and DTO shape.
