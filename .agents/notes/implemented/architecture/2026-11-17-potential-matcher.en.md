# Agent Note: PotentialMatcher and the three-stage preview

Status: implemented

English | [中文](2026-11-17-potential-matcher.md)

## Problem

Wizard steps 2–4, future run prepare, and the object overview all answer the same questions: which Sessions contain the object, which bad cases are potential, and which attributions can reuse cache. Separate queries and policies in each place would drift on Session counts, version identity, and policy exclusion, and the two empty states ("no associated Session" vs "zero potential") would be indistinguishable. M9 already persists object events, versions, and trigger coordinates in `agent_events`, but knowledge events only guarantee `document_revision`; preview must also stay read-only and must not execute attribution. One shared, read-only implementation is needed, and knowledge objects plus coordinate comparison must live in the same slice.

## Decision

- One implementation: `PotentialMatcher` lives in `service/evolution/potential.py` and owns `associated_sessions`, `potential_cases`, and `attribution_preview`; `db/crud/potential.py` only provides chunked batch reads (window cases, session metadata, object events, agents, anchor events, cache keys, non-target counts) and never issues per-case queries. The preview service only normalizes the condition, paginates, and maps DTOs; it never re-derives policy.
- Object types: `EvolutionTargetWrite`, the target record, and the target DTO accept `skill|agent|knowledge`; `bad_cases.object_type` and the first attribution engine's `probe_type` stay `skill|agent`. Knowledge targets use the existing target CRUD, while the wizard catalog does not expose them yet (no selector); m10-04 wires the run.
- Object entry: `kind` maps to `object_type` (skill/agent/knowledge), requiring `name == target.name` and `object_version == resolved version`; the earliest event wins, ordered by `triggered_at` and falling back to `(tree_index, event_index)`. A Session whose events only carry NULL versions enters `versionUnresolved`; neither name-level guessing nor knowledge `document_revision` substitution is allowed.
- Session partition: `reported = associated + versionUnresolved + skipped + pending`, non-overlapping; `pending` is a reported root without a `session_families` row. Step 2 lists only `associated`, and its `potentialCount` uses the default policy.
- Policy: default is exactly `(object_name == target.name AND bad_case_type='self') OR (case_trigger > object_enter)`, and carrying any switch is `422 POLICY_INVALID`; custom requires all three switches and at least one enabled matching rule, takes the union of enabled rules, then applies `sameObjectOnly`. `sameObjectOnly` compares only `object_name == target.name` because `bad_cases.object_type` has no `knowledge`. The closed hit reasons are `self_report|after_object|both|policy_excluded|order_unknown`; excluded rows are counted in `byReason` but never listed in `items`.
- Anchors and comparison: bad-case anchors follow 06 §7.4; skill uses the reporter's last same-name trigger, `discovery+agent` uses the parent's `tool_use_id`-matched call, and a missing anchor degrades to the reporter birth point (session `started_at` for the main Agent, the parent call for a subagent). An unresolvable reporter stays `unknown` rather than guessing a position via the main Agent. Both `triggered_at` values present means strict time comparison; otherwise `(tree_index, event_index)` lexicographic order applies; incomplete coordinates mean `order_unknown` and never "after".
- Window and cache: Asia/Shanghai day boundaries over `bad_cases.created_at`; no `from/to` means the last 90 days; `from > to` or more than 366 days is `422 WINDOW_INVALID`. Attribution preview reads existing cache keys only, computing them with `policy_version=v1` and attribution engine `rule-v1`; `cacheEnabled=false` makes `reused=0`; `nonTargetKnown` is the distinct historical case count with `conclusion='non_target'` for this object/version.
- API: the three `POST /api/workspaces/{wid}/evolution/preview/{sessions,potential,attribution}` endpoints require at least `viewer`; the target must be enabled inside the workspace (otherwise `409 TARGET_NOT_CONFIGURED`), no associated Session (all three) is `409 NO_ASSOCIATED_SESSIONS`, and zero potential (steps 3 and 4) is `409 NO_POTENTIAL_MATCHED`. `engineKey` is only validated as registered (`422 ENGINE_INVALID`); preview never executes it. All three are read-only and never write `probe_reports`, `bad_case_analysis`, or `evolution_run_candidates`.

## Alternatives considered

- **Queries and policy per endpoint**: the three counts would inevitably drift and could not guarantee one metric for wizard, run, and overview; rejected in favor of one matcher plus a batch repository.
- **Guess the version by name or `document_revision`**: same-name/different-version traces would be counted as associated and knowledge would bypass the shared version rule; rejected, NULL versions only enter `versionUnresolved`.
- **Execute attribution and write cache during preview**: preview would gain side effects and break the read-only promise and cache audit; rejected, it only counts existing keys.
- **Put knowledge into the wizard catalog immediately**: this slice has no UI selector, so the catalog would expose an unusable entry; rejected, target CRUD supports it while the catalog stays skill/agent.
- **Degrade a missing reporter to the main Agent**: that manufactures a definite order out of an unknown position; rejected, it stays `unknown`.
- **Create a separate preview candidate/snapshot table**: a candidate is a run-level fact and preview has no run, so early rows would be orphaned; rejected, m10-04 lets prepare write `evolution_run_candidates`.

## Consequences

- m10-04 run prepare and any future overview must build the same `MatchCondition` and call `PotentialMatcher`; policy and coordinate logic must not be copied.
- Knowledge association depends on `agent_events.object_version`; the current M9 parser only guarantees `document_revision`, so real knowledge events usually stay in `versionUnresolved` until a version exists. This is a known limitation, not a reason for a name-level fallback.
- Policy semantics stay at version `v1`; changing the attribution engine or the cache-key composition requires updating the preview's `ATTRIBUTION_ENGINE` together with the migration contract.
- `sameObjectOnly` filters by name only; if `bad_cases.object_type` ever accepts knowledge, whether type joins the same-object test must be re-evaluated.
- The three preview endpoints have no UI change; the wizard, catalog, and target form still expose only skill/agent, and knowledge run wiring is m10-04's job.
