# Add a .env switch: name matching for skill evolution targets (off by default, reusing the agent switch)

English | [中文](bugfix-skill-name-match-toggle.md)

```yaml flow
kind: issue
id: bugfix-69
milestone: bugfix
depends:
  - m13-01
  - m11-03
  - m11-04
priority: P2
status: ready
scope:
  - .agents/**
  - .env.example
  - apps/api/app/config.py
  - apps/api/app/main.py
  - apps/api/app/service/evolution/**
  - apps/api/app/service/overview/**
  - apps/api/tests/**
  - docs/architecture.md
  - docs/architecture.en.md
  - docs/architecture.i18n.yaml
  - plans/fullstack-design/05-api-design.md
  - plans/fullstack-design/06-database-design.md
  - plans/fullstack-design/07-backend-implementation.md
  - plans/fullstack-design/08-frontend-implementation.md
adr: []
github:
  number: 648
  url: https://github.com/Shadow-Azure/harness-evolution/issues/648
```

## Background

The requester wants another `.env` matching switch, off by default; when it is enabled, skill evolution targets should stop matching by the definition-body digest and match by "object type + name" instead. The requester explicitly asked to reuse the already implemented agent switch (`HE_AGENT_MATCH_BY_NAME`, issue #632 / PR #636) and unify the skill and agent name-matching design.

Today both skill and agent version identity is the normalized definition-body hash, not the name:

- Target version resolution reads `SKILL.md` at the selected ref and computes `targetRevision=digest:<sha256(normalize_definition_body(body))>` with `definition_file_hash` (`apps/api/app/service/evolution/target_content.py`). A failed read returns `TARGET_CONTENT_UNRESOLVED`; it never falls back to a name.
- A skill trigger event gets `object_revision=digest:<body hash>` from the parser (`_skill_revision` in `apps/api/app/service/acquisition/parsers/base.py`); an opaque listing digest is only a fallback when no body evidence exists. `definition_hash` is the bare body hash.
- Wizard steps 2/3 and the pre-launch potential check already omit `observed_revisions` and associate by type + name. Overview target analysis (object list, trends, case list and detail all use `_analyse_target`) passes `condition.revision_candidates` to `PotentialMatcher.associated_sessions`, requiring an event's `object_version`/`object_revision`/`definition_hash`/`document_revision` to hit a selected version (`apps/api/app/service/overview/targets.py`, `apps/api/app/service/evolution/potential.py`).
- Consequently the same skill name can be split into several digest rows in the overview: the configured-ref row filters to zero Sessions while same-name traces exist, and a changed skill body cannot be aligned. Overview and wizard use two different matching rules.
- The agent switch is already scoped to `object_type=agent`; skill still takes the hash branch. Both the matcher and the overview service carry their own `agent_match_by_name` boolean, wired independently from `main.py`. This duplicated type check is the natural place to unify into one target-type set when the skill switch is added.

Name matching folds same-name, different-body skills into one object and sacrifices version precision. It must therefore remain an explicit, configurable, off-by-default exception; the default stays body hash and the existing "never guess a name for an unknown revision" decision is unchanged. The requester's "md5sum" is actually a SHA-256 normalized body hash in the code; this issue describes the existing `digest:` identity and introduces no new algorithm.

## Goals

- Add an optional environment variable `HE_SKILL_MATCH_BY_NAME`, boolean, default `false`; it is read at API startup and requires a `harness-api` restart after changes.
- Off (default): skill behavior stays byte-for-byte identical, including body-hash identity, overview version rows, association counts, error codes and existing tests.
- On: only for targets with `object_type=skill`, Session association and overview version rows match by "object type + name" and stop filtering on `definition_hash`/`object_revision`; one skill target shows a single configured version row (`defaultRef`) and all same-name Sessions are included.
- With the switch on, historical attribution reports stay attached to that single skill row (newest report per case); version folding must not hide them or zero their counts.
- Reuse and unify the agent switch implementation: keep the existing `HE_AGENT_MATCH_BY_NAME` name and semantics at the configuration boundary, but use one `name_match_types` set internally so skill and agent share the same matching and version-folding code path; adding a future type only adds it to the set instead of copying boolean branches.
- The two switches are independent: skill-only leaves agent on the hash rule, agent-only leaves skill on the hash rule; knowledge targets are never affected.
- Report content identity, `targetRevision`, frozen source, run snapshots, cache keys and step-4 statistics still use the body hash; the switch only changes the matching and version-row layer, not report bodies or cache scope.
- Event ingestion, database schema, OpenAPI contracts and frontend forms stay unchanged; historical digest versions and reports remain readable with no backfill or rewrite.

## Design authority

- [05 §4.20 Self-evolution preview and launch (V2)](../../../plans/fullstack-design/05-api-design.md#420-自进化预览与启动v2): `targetRevision` only freezes source, reports and cache scope; Session association uses object type and name appearance. This issue extends that rule from agent to skill behind an explicit switch.
- [05 §4.18 Overview and workspace Session list (V2)](../../../plans/fullstack-design/05-api-design.md#418-总览与空间-session-列表v2): object-card version identity and the `byVersion` contract; with the switch on, the affected type's version key becomes the single configured ref.
- [06 §5.1 evolution_targets](../../../plans/fullstack-design/06-database-design.md#51-evolution_targets--可自进化的对象配置): target type, `defaultRef` and binding fields; neither switch adds a column.
- [06 §7.5 V2 semantics](../../../plans/fullstack-design/06-database-design.md#75-v2-口径空间--触发点--潜在--归因三态): object appearance and entry points, potential and attribution states.
- [07 §5.12 Potential matching](../../../plans/fullstack-design/07-backend-implementation.md#512-潜在匹配serviceevolutionpotentialpy): the query and filtering point of `PotentialMatcher`; skill and agent share one association path.
- [08 §9.5 Evolution target configuration page](../../../plans/fullstack-design/08-frontend-implementation.md#95-进化对象配置页evolutiontargets): version and overview entry points; this issue adds no form field.
- Agent Note [Body hash by default, explicit switch for agent name matching](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/architecture/2026-11-26-agent-name-match-switch.md): the existing trade-offs and the "only association and version rows, never report identity" boundary; this issue generalizes it into a target-type set.
- Agent Note [Attribution identity as normalized body hash and the post-process anchor](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/architecture/2026-11-18-body-hash-attribution-post-process.md): the body-hash decision and the original reasons for rejecting name-only matching; this switch remains a bounded, off-by-default exception.

## Implementation

### Configuration

- Add `skill_match_by_name: bool = False` to `Settings` in `apps/api/app/config.py`, read through the `HE_` prefix. Keep `agent_match_by_name: bool = False` with its existing name, default and semantics.
- Add a read-only derived `name_match_types` property on `Settings` returning the enabled target types (`agent` when `agent_match_by_name` is true, `skill` when `skill_match_by_name` is true, never knowledge). Invalid booleans still fail startup through Pydantic.
- Add `# HE_SKILL_MATCH_BY_NAME=false` next to `HE_AGENT_MATCH_BY_NAME` in `.env.example`, documenting that it only affects skill association and overview version rows, is off by default, keeps reports/cache/`targetRevision` on the body hash, and needs a `harness-api` restart.
- Do not add a third master switch. Operations keep two independent booleans; unification happens inside the code so an already deployed `HE_AGENT_MATCH_BY_NAME` is neither renamed nor silently ignored.

### Shared type set

- Change `PotentialMatcher`'s constructor argument from `agent_match_by_name: bool = False` to `name_match_types: frozenset[str] = frozenset()`; the empty default keeps other call sites unaffected.
- Change `TargetOverviewService` the same way. Pass `resolved_settings.name_match_types` at all three `main.py` construction sites (preview matcher, long-lived matcher, overview service).
- Change the `PotentialMatcher.associated_sessions` branch to `ignore_revisions = event.object_type in self._name_match_types`; skill and agent no longer carry separate booleans, and knowledge is absent from the set so it is unchanged.
- Change the `TargetOverviewService._analyse_target` decision to `name_matched = target.object_type in self._name_match_types`.
- Make the agent-specific naming type-neutral: rename `_agent_name_aliases` to `_name_match_aliases`, and update the comments/docstrings of `_name_matched_version`, `_name_match_commit` and the `match_by_name` argument to cover both skill and agent without changing the algorithm.
- Update unit-test construction from `agent_match_by_name=True` to `name_match_types=frozenset({"agent"})` so tests stop pinning the old boolean interface.

### Matching and overview

- When the switch is on and the target is a skill, `TargetOverviewService` reuses `_name_matched_version`: it builds one row keyed by `defaultRef` and still resolves `SKILL.md` to render ref/revision/commit; a resolution failure only drops the commit and does not block name association.
- The row's alias set covers the configured ref, resolved revision, bare body hash and historical report `object_version` values; `_newest_link_by_case` keeps the newest report per case so existing attributed/nonTarget counts never drop to zero because of folding.
- When the switch is on and the event type is skill, `PotentialMatcher` ignores the supplied `observed_revisions` and associates every same-name Session in the window by type + name; event versions remain as evidence but do not participate in selection.
- Multi-member configurations: `_analyse_config` already calls `_analyse_target` per member, so the switch applies per member type. In a skill-only switch, skill members fold into one row while agent members keep their digest rows; `_merge_analyses` union/dedup behavior is unchanged.
- Wizard steps 2/3 and the pre-launch potential check already do not filter by revision; add a regression assertion that both switches leave their behavior unchanged. Launch, reports and cache still use `targetRevision` with no name fallback.
- Skill and knowledge default paths stay unchanged; with both switches off, `_build_version_labels` output, counts and error codes are byte-for-byte identical.

### Documentation and decisions

- Update `docs/architecture.md` and its English pair so "never guess a name" says skill/agent name matching is controlled by `HE_SKILL_MATCH_BY_NAME` / `HE_AGENT_MATCH_BY_NAME` respectively, off by default; run `pnpm record:i18n -- docs/architecture.md` to re-record the pair.
- Extend the 05/06/07/08 design notes that currently mention only `HE_AGENT_MATCH_BY_NAME` to both switches, stating that each only affects its own type's association and overview version rows while reports and cache remain on the body hash.
- Add an Agent Note (`implemented/architecture`) recording the "two environment booleans, one internal type set" decision, the precision trade-off for same-name different-body objects, and why a single list-valued environment variable was not used to replace existing deployments. Update the existing agent-switch note's "skill is unaffected" sentence to "skill is unaffected when only the agent switch is on" so the two notes agree.
- Backfill the new Agent Note path into this issue's `adr`.

## Implementation steps

1. Add `skill_match_by_name` and the derived `name_match_types` property to `Settings`, with config tests for unset/false/true/both/invalid; update `.env.example`.
2. Replace the boolean parameters of `PotentialMatcher` and `TargetOverviewService` with `name_match_types` and update all three `main.py` wiring sites; add matcher tests for skill/agent/both/knowledge and confirm existing agent assertions still pass.
3. Reuse `_name_matched_version` and the alias logic for skill, with overview API/unit tests: default multi-row digest behavior unchanged; skill-only yields one skill row that includes same-name different-hash Sessions and keeps historical report counts; agent-only leaves skill unchanged; verify both switches and mixed-member configurations separately.
4. Update `docs/architecture` and 05/06/07/08 design docs, add the Agent Note and backfill `adr`, then run doc pairing and flow gates.
5. With one fixture, viewport and theme, call the overview detail with both switches off and with skill only on, capture before/after evidence, and record skill version-row counts, associated Sessions and historical report attachment.
6. Run this issue's verification commands, commit, and open a PR whose description states the default-off compatibility evidence, the skill switch comparison and any limitations.

## Dependencies and boundary

- Dependencies: m13-01 (body-hash identity), m11-03 (overview API), m11-04 (overview UI); all are done.
- Compatible with same-repo multi-member configurations: the switch applies per member `object_type`, not once per configuration; this issue does not change the member model.
- Delivery boundary: one environment variable, the configuration type set, the shared matcher filter, overview version aggregation and historical report aliases. No database change, no OpenAPI change, no event-write change, no change to target/run `targetRevision`, report cache keys or step-4 statistics.
- Do not change `TargetContentResolver`/`TargetDefinitions`: `SKILL.md` remains required for launch and attribution, a failed read still raises explicitly, and a name is never used to guess content.
- Do not modify historical rows, migrate, backfill or recompute historical reports; either switch can be turned off at any time to restore hash semantics.

## Verification

```sh
pnpm test:api -- tests/bugfix-skill-name-match tests/bugfix-agent-name-match tests/m10-02-potential-matcher tests/m11-03-target-overview
pnpm lint:api
pnpm typecheck:api
pnpm contract:check
pnpm verify:flow
pnpm verify:docs
```

- Config tests: unset/false yields an empty `name_match_types`; `HE_SKILL_MATCH_BY_NAME=true` alone yields `{"skill"}`; agent alone yields `{"agent"}`; both yield both; an invalid value fails startup validation.
- Matcher tests: with the skill switch on, skill ignores `observed_revisions` and includes same-name Sessions with a different `definition_hash`; with the agent switch off, agent remains hash-filtered; knowledge ignores either switch.
- Overview tests: by default skill keeps its current digest version rows; skill-only collapses a skill target to one `defaultRef` row that includes same-name different-hash Sessions and historical reports without zeroing counts; agent-only leaves skill assertions unchanged; both switches and mixed-member configurations stay independent.
- Documentation gates: `docs/architecture` is re-recorded in both languages and `pnpm verify:docs` plus `pnpm verify:flow` pass; the Agent Note and `adr` are filled in.
- Browser check: with one fixture, viewport and theme, the default shows skill digest rows and skill-only shows one configured-ref row; attach screenshots to the PR description.

## Acceptance

1. With `HE_SKILL_MATCH_BY_NAME` unset or `false`, skill association counts, overview version rows, step-4 statistics and error codes are byte-for-byte identical and existing tests need no assertion changes.
2. With `HE_SKILL_MATCH_BY_NAME=true` and a restart, a skill target detail has one configured-version row; same-name Sessions count even when their `definition_hash` differs from the target body hash, and same-name digest rows no longer appear.
3. Skill-only leaves agent targets unchanged; agent-only leaves skill targets unchanged; enabling both folds each type independently; knowledge targets never change.
4. With the switch on, historical reports remain attached to the single row per case and attributed/nonTarget counts do not drop to zero through folding or missing aliases. Step-4 `reused/fresh` and `nonTargetKnown` remain governed by the body-hash report scope, and report bodies, `targetRevision` and run snapshots are not rewritten.
5. In a same-repo multi-member configuration, the switch folds only members of enabled types; other members keep digest rows and the merged Session/case union loses nothing.
6. With the switch on, the overview still tries to resolve `SKILL.md` for ref/commit; if resolution fails the overview may associate by name, but launch still returns the existing `TARGET_CONTENT_UNRESOLVED`. Name matching never bypasses content reading.
7. Turning the switch off restores hash semantics; historical digest versions and reports remain readable without migration.
8. Durable docs are updated and re-recorded in both languages; the new Agent Note records the unified trade-off and `adr` is backfilled; `pnpm verify:flow` and `pnpm verify:docs` pass.

## Gates and CI

- API: `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test:api -- tests/bugfix-skill-name-match tests/bugfix-agent-name-match tests/m10-02-potential-matcher tests/m11-03-target-overview`.
- Contracts: `pnpm contract:check` has no diff when no API field changes; if the implementation unexpectedly touches a DTO, update the 05 design and regenerate first.
- Docs: `pnpm lint:docs`, `pnpm verify:docs`; after changing `docs/architecture` in both languages run `pnpm record:i18n -- docs/architecture.md`.
- Flow: commit and PR titles contain `(#N)`; the implementation PR opens only after this issue is `in-progress`; `pnpm verify:flow` and `pnpm verify:flow -- --diff origin/main` pass.
- UI-visible change: the PR description carries before/after screenshots with the same fixture, viewport and theme, explicitly identifying the baseline (both switches off) and the change (skill only on); after-only evidence is incomplete.
- Agent Note: record the decision and backfill this issue's `adr`; do not commit run logs, production Sessions or credentials.

## Non-goals

- Do not move skill `targetRevision`, report cache keys, frozen source or step-4 statistics from the body hash to the name; same-name different-body reports must still be distinguished by content.
- Do not change `TargetContentResolver`/`TargetDefinitions` read/error behavior or guess content from a name or default branch.
- Do not change knowledge matching or introduce a global "name first, hash fallback" automatic fallback.
- Do not rename the agent switch or replace the two booleans with a single list-valued environment variable; this issue only unifies the internal code path and keeps operations backward compatible.
- Do not add a UI switch, form field or contract field, and do not change deployment injection; production configures the server `.env` and restarts.
- Do not migrate, backfill or recompute historical version rows or reports, and do not change event ingestion or parser algorithms.
