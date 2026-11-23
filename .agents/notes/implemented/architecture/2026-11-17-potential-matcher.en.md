# Agent Note: PotentialMatcher and the three-stage preview

Status: implemented

English | [中文](2026-11-17-potential-matcher.md)

## Problem

Binding workers, previews and Runs need the same answer about object presence across the Session tree. Historical traces can lack a revision or record a different one from the source selected for analysis. Both observed and selected identities matter for reproducibility.

## Decision

- One implementation: `PotentialMatcher` lives in `service/evolution/potential.py` and owns `associated_sessions`, `potential_cases`, and `attribution_preview`; `db/crud/potential.py` only provides chunked batch reads (window cases, session metadata, object events, agents, anchor events, cache keys, non-target counts) and never issues per-case queries. The preview service only normalizes the condition, paginates, and maps DTOs; it never re-derives policy.
- Associate a Session by the type and name of an object event anywhere in its tree. In the absence of a call event, an agent node type (or name if missing) or an explicit node skill name establishes presence. Match each object type independently.
- Preserve observed versions and coordinates in the context. The selected target revision pins the source, report and cache scope. Node evidence references the node itself. Historical overview buckets restrict the observed revision so a Badcase is not multiplied across versions.
- Object types: `EvolutionTargetWrite`, the target record, and the target DTO accept `skill|agent|knowledge`; `bad_cases.object_type` stays `skill|agent`, and `probe_reports.probe_type` accepts knowledge ahead of m10-03's knowledge attribution writes. A knowledge target's `defaultRef` accepts revision forms; create/update skip git `ls-remote`, and `versions` returns an empty list plus `defaultRef`. The wizard catalog and target form do not expose knowledge yet (no selector), and run launch still accepts only skill/agent; configurable is not launchable, and m10-04 wires the run.
- New association partitions contain associated Sessions, skipped Sessions and pending traces. The compatibility field `versionUnresolved` is zero. Step 2 paginates associated Sessions and preserves the 409 with counts for an empty result.
- Policy: default is exactly `(object_name == target.name AND bad_case_type='self') OR (case_trigger > object_enter)`, and carrying any switch is `422 POLICY_INVALID`; custom requires all three switches and at least one enabled matching rule, takes the union of enabled rules, then applies `sameObjectOnly`. Both `self` and `sameObjectOnly` compare only `object_name`, not `bad_cases.object_type` or `object_version`; same-name skill/agent reports and cross-version self reports are included. The closed hit reasons are `self_report|after_object|both|policy_excluded|order_unknown`; excluded rows are counted in `byReason` but never listed in `items`.
- Anchors and comparison: bad-case anchors follow 06 §7.4; skill uses the reporter's last same-name trigger, `discovery+agent` uses the parent's `tool_use_id`-matched call, and a missing anchor degrades to the reporter birth point (session `started_at` for the main Agent, the parent call for a subagent). A blank reporter id counts as absent and falls back to the main Agent; a non-empty Agent must belong to the same Session, and a subagent with an unresolved parent does not borrow the Session start and stays `unknown`. Both `triggered_at` values present means strict time comparison; otherwise `(tree_index, event_index)` lexicographic order applies; incomplete coordinates mean `order_unknown` and never "after". Selecting the earliest object entry uses the same rule (time only when both sides have it), so a later timestamped event is not treated as earlier than an untimestamped one.
- Window and cache: Asia/Shanghai day boundaries over `bad_cases.created_at`; no `from/to` means the last 90 days; `from > to` or more than 366 days is `422 WINDOW_INVALID`. Attribution preview accepts no `engineKey` and executes no engine. Bound-package mode reads the latest completed report per case via `bad_case_analysis` (`analyzed_at`), groups `bySkill` by `attribution_skill_name`, and sets `missing=potential-reused`; `cacheEnabled=false` makes `reused=0`, `fresh=potential`, and `missing=0`. Only legacy rule mode reads existing cache keys computed from the resolved `targetRevision`, `policy_version=v1`, and attribution engine `rule-v1`. `nonTargetKnown` counts distinct historical cases with `conclusion='non_target'` queried by both `targetVersion` and `targetRevision`, is a reference figure, and may overlap `reused`.
- API: the three `POST /api/workspaces/{wid}/evolution/preview/{sessions,potential,attribution}` endpoints require at least `viewer`; the target must be enabled inside the workspace (otherwise `409 TARGET_NOT_CONFIGURED`), no associated Session (all three) is `409 NO_ASSOCIATED_SESSIONS` plus summary, and zero potential (steps 3 and 4) is `409 NO_POTENTIAL_MATCHED`. All three are read-only and never write `probe_reports`, `bad_case_analysis`, or `evolution_run_candidates`.

## Alternatives considered

- Requiring the snapshot revision for admission drops historical Badcases with direct evidence that the object ran.
- Backfilling observed versions from the selected revision would misstate historical evidence. Reports and cache entries record the chosen source, while unknown trace versions stay unknown.
- **Keep git validation for knowledge targets**: knowledge documents are not necessarily git objects, so admins would have to invent a remote that passes `ls-remote`; rejected, knowledge skips git validation and returns an empty version list.
- **Queries and policy per endpoint**: the three counts would inevitably drift and could not guarantee one metric for wizard, run, and overview; rejected in favor of one matcher plus a batch repository.
- **Step 2 returns 409 without summary, or a 200 empty page**: the former loses the `versionUnresolved` explanation and the latter contradicts the existing 409 contract; rejected, keep the 409 and put the five numbers in `details.summary`.
- **Keep `engineKey` on preview**: it validates the run-engine registry while the cache key is fixed to an attribution engine, so the meaning is ambiguous; rejected, remove the field and never execute an engine in preview.
- **Compute full potential for four Session rows**: moving the whole library for the book covers; rejected, step 2 only associates and `potentialCount` remains for m10-04's run step.
- **Compare type or version in self/sameObjectOnly**: product has not confirmed tightening and 06 §7.5 says name-only; rejected, keep name-only and lock it in docs/tests.
- **Create a separate preview candidate/snapshot table**: a candidate is a run-level fact and preview has no run, so early rows would be orphaned; rejected, m10-04 lets prepare write `evolution_run_candidates`.

## Consequences

- m10-04 run prepare and any future overview must build the same `MatchCondition` (including `target_revision`) and call `PotentialMatcher`; identity, policy, and coordinate logic must not be copied.
- Historical Runs keep their saved counts. New bindings and wizard previews share the presence-based selection.
- Policy semantics stay at version `v1`; changing the attribution engine or cache-key composition requires updating the preview's `ATTRIBUTION_ENGINE` together with the migration contract.
- `sameObjectOnly` and self use name only; same-name different-type or cross-version reports are included. If `bad_cases.object_type` ever accepts knowledge or product tightens the rule, re-evaluate with migration tests.
- Knowledge targets can be configured and previewed only through the API; catalog, target form, and run launch still support skill/agent only, with selector and run wiring left to m10-04.
- Previews and the prototype must share the presence contract: 05/06/07/08 must not describe Session association as identity matching; the prototype's step-4 `attributionSkill` must persist with the Run, and Run detail and step 4 must share reuse/fresh/missing counts. Step 2's 409 `details.summary` is the only source for the wizard empty state.
