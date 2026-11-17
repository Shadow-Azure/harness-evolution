# Agent Note: Four-step launch wizard and launch condition snapshot

Status: implemented

English | [中文](2026-11-17-four-step-launch-wizard.md)

## Problem

The V1 wizard had only two steps, "filter problem reports" and "confirm hits", and it drew its hits from legacy probe reports. It could not express the V2 chain "which Sessions contain the target version → which bad cases are potential → how much attribution cache can be reused". Recomputing version association, potential membership, or cache reuse in the browser would give the wizard, error-detail page, and run-detail page separate definitions, so the preview counts and the launched run would disagree. Conversely, if each preview step executed attribution, step 4 would write before the user confirms, breaking the read-only preview contract.

## Decision

- `LaunchWizard.vue` is a four-step state machine: range → Session association → potential bad cases → attribution preview and launch. Steps 2–4 only consume the server summaries and page rows from `preview/sessions`, `preview/potential`, and `preview/attribution`; the browser never recomputes potential membership or hit reasons.
- Step 1 is the only place that edits conditions. Changing the target, version, window, or policy clears later previews and returns to step 1; pagination on steps 2 and 3 re-requests only that endpoint's `page` and never reruns an earlier stage.
- Policy has two shapes: `{preset:"default"}` or `{preset:"custom", includeSelfReport, includeAfterObject, sameObjectOnly}`. A custom policy must enable at least one matching rule; client validation and the backend `422 POLICY_INVALID` share that rule. Policy is editable only in step 1 so step 3 cannot silently change the potential set while keeping stale pagination.
- `409 NO_ASSOCIATED_SESSIONS` renders the five-way partition from `details.summary` and disables forward navigation; `409 NO_POTENTIAL_MATCHED` renders the step-3 empty state and also disables forward navigation. Empty stages never fake a `200` empty page.
- The step-4 cache switch defaults on, and toggling it re-requests the read-only attribution preview. The four numbers come directly from `{potential, reused, fresh, nonTargetKnown}` and are never added together. The two exits keep the `cluster_only` and `full` `202` acceptance semantics.
- The launch request submits the selected policy and cache switch with the condition. `resolve_policy` validates and expands `policy`, and `potential_policy` plus `cacheEnabled` are frozen on the `evolution_runs` row. The run therefore uses the same potential set and cache strategy that step 4 showed instead of reading the caller's later values during prepare.
- `focusCaseId` arrives through `?case=` or a component prop: the wizard reads the workspace-scoped bad case, preselects its object and version, and shows a read-only hint. It does not change potential semantics and does not widen the window automatically. The error-detail button is wired by m11-02; this slice provides the entry capability.
- The step-2 table has four columns, "Session / object presence / object trigger time / bad-case count", and deliberately no potential count: that endpoint only associates Sessions, while potential counts belong to step 3.

## Alternatives considered

- **Recompute the potential set in the browser from bad-case rows**: it would drift from `PotentialMatcher` self/after_object, coordinate ordering, and sameObjectOnly semantics. Rejected; every count comes from a server summary.
- **Split steps into four dialogs or routes**: conditions would be copied across pages and invalidation after edits would be harder to guarantee. Rejected; keep one dialog and one state machine.
- **Let the cache switch change copy only and omit it from launch**: the run snapshot would disagree with the preview (preview says reuse, run recomputes). Rejected; `policy` and `cacheEnabled` are part of the launch body and run snapshot.
- **Allow policy edits in step 3**: that silently changes the potential set while keeping old pages. Rejected; policy edits return to step 1 and re-preview.
- **Treat empty stages as generic empty pages**: it discards the five-way Session partition and leaves users unable to explain why nothing was associated. Rejected; keep the 409 and explain it from details.
- **Prefill the window from the focus case date**: a one-day window changes potential semantics. Rejected; only object and version are preselected.

## Consequences

- `policy`/`cacheEnabled` on the launch body is an input contract for the m10-04 seven-step prepare; this slice lands the contract and the run snapshot, while the consuming pipeline remains m10-04. Until m10-04 merges, the legacy prepare still runs on probe hits, so the step-4 potential count is not yet the legacy pipeline's input.
- `preview/attribution` is read-only: it writes no `probe_reports`, `bad_case_analysis`, or candidates. The step-4 `fresh` value is potential minus reused, not a count of already-created attributions.
- The cache key contains the resolved `targetRevision`, policy version, and attribution engine; different revisions of one object do not reuse each other, and the historical non-target count is only a reference.
- The E2E suite runs the real API with SQLite and the fixture corpus, then patches the skill event's `object_version`/`object_revision`/`triggered_at` and the target `default_ref`. Fixture events do not carry object versions; that is a test-fixture boundary.
- The asynchronous prepare after launch may fail, for example when a test remote is unreachable. The wizard is only responsible for the `202` acceptance; run detail, blocked state, and retry stay in later slices.
