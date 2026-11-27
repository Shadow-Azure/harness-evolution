# Add a per-member switch: skill/agent name matching in the evolution member editor (off by default)

English | [中文](bugfix-skill-name-match-toggle.md)

```yaml flow
kind: issue
id: bugfix-73
milestone: bugfix
depends:
  - m13-01
  - m11-03
  - m11-04
priority: P2
status: in-progress
scope:
  - .agents/**
  - .env.example
  - apps/api/alembic/**
  - apps/api/app/api/**
  - apps/api/app/config.py
  - apps/api/app/db/**
  - apps/api/app/main.py
  - apps/api/app/service/evolution/**
  - apps/api/app/service/overview/**
  - apps/api/tests/**
  - apps/web/src/**
  - packages/contracts/**
  - docs/architecture.md
  - docs/architecture.en.md
  - docs/architecture.i18n.yaml
  - plans/fullstack-design/05-api-design.md
  - plans/fullstack-design/06-database-design.md
  - plans/fullstack-design/07-backend-implementation.md
  - plans/fullstack-design/08-frontend-implementation.md
  - plans/ui-prototype-v2/**
  - tests/e2e/**
adr:
  - ../../notes/implemented/architecture/2026-11-27-member-name-match-switch.md
github:
  number: 648
  url: https://github.com/Shadow-Azure/harness-evolution/issues/648
```

## Background

On 2026-11-27 the requester added a requirement: make both agent and skill matching a switch inside the "sub-evolution-object editor", configured per evolution-object member rather than per `.env` deployment. The previous two-environment-variable plan (`HE_AGENT_MATCH_BY_NAME` and a proposed `HE_SKILL_MATCH_BY_NAME`) is retired. This issue now uses a member-level `matchByName` field. The prototype and issue update landed in #651; this implementation PR delivers the database, API, matcher, run snapshots, and frontend switch.

Key facts about the current matching path:

- Skill/agent version identity is the normalized definition body hash (`digest:<sha256(normalize_definition_body(body))>`), not the name; both target version resolution and event `object_revision` use it (`target_content.py`, `acquisition/parsers/base.py`).
- Overview `_analyse_target` passes `condition.revision_candidates` to `PotentialMatcher.associated_sessions`, filtering on `object_version`/`object_revision`/`definition_hash`/`document_revision`. Same-name objects with different bodies therefore split into several rows, and the configured-ref row can show zero Sessions.
- Wizard and launch currently pass no revision filter and associate by object type + name; overview and wizard/launch use two different rules.
- The implemented `HE_AGENT_MATCH_BY_NAME` applies only to agent and is a deployment-level boolean. It switches every agent on a deployment together and cannot vary between members of one configuration. Skill still takes the hash branch.
- The member editor already edits type, name and subdirectory per member. Putting a `matchByName` switch on that row reuses the existing member model without a new configuration page or a second master switch.

Name matching folds same-name, different-body objects into one identity and sacrifices version precision, so it must be off by default and explicitly opted in. The requester's "md5sum" is actually a SHA-256 normalized body hash in the code; this issue keeps the existing `digest:` identity and introduces no new algorithm.

## Goals

- Add a "name matching" switch to every member row in the evolution-target editor, persisted as member field `matchByName`, boolean, default `false`; show it only for skill/agent members, never for knowledge.
- Off (default): the member still matches by definition body hash; overview version rows, association counts, error codes and existing tests stay unchanged.
- On: only that member associates and renders overview rows by object type + name instead of filtering on `definition_hash`/`object_revision`; it shows one configured version row (`defaultRef`), all same-name Sessions count, and historical reports reattach through aliases.
- Members of one configuration can switch independently: skill-only leaves agent members on digest matching and vice versa; multi-member `_merge_analyses` union/dedup behavior is unchanged.
- Remove `HE_AGENT_MATCH_BY_NAME` and any `skill_match_by_name` configuration entry; add no new environment variable. Matching mode is persisted with member config and does not require a `harness-api` restart.
- Report content identity, `targetRevision`, frozen source, run snapshots, cache keys and step-4 statistics still use the body hash; the switch only changes the association and version-row layer.
- Update the V2 prototype and design note, and put same-scenario, same-viewport, same-theme before/after screenshots into this issue.
- The prototype, design-note and issue changes landed in #651; this implementation PR delivers the database, API, frontend and matcher.

## Design authority

- [05 §4.20 Self-evolution preview and launch (V2)](../../../plans/fullstack-design/05-api-design.md#420-自进化预览与启动v2): `targetRevision` only freezes source, reports and cache scope; Session association uses object type and name appearance. This issue moves that rule into a member-level switch.
- [05 §4.18 Overview and workspace Session list (V2)](../../../plans/fullstack-design/05-api-design.md#418-总览与空间-session-列表v2): object-card version identity and the `byVersion` contract; with the switch on, the member's version key becomes the single configured ref.
- [06 §5.1 evolution_targets](../../../plans/fullstack-design/06-database-design.md#51-evolution_targets--可自进化的对象配置): target, member and `defaultRef` fields; this issue adds one boolean to the member table, not a deployment-level column to the target table.
- [06 §7.5 V2 semantics](../../../plans/fullstack-design/06-database-design.md#75-v2-口径空间--触发点--潜在--归因三态): object appearance and entry points, potential and attribution states.
- [07 §5.12 Potential matching](../../../plans/fullstack-design/07-backend-implementation.md#512-潜在匹配serviceevolutionpotentialpy): the query and filtering point of `PotentialMatcher`; `MatchTarget` must carry each member's own switch.
- [08 §9.5 Evolution target configuration page](../../../plans/fullstack-design/08-frontend-implementation.md#95-进化对象配置页evolutiontargets): member-row editing and submission; this issue adds a switch to the member row, not a separate page.
- [V2 prototype design §5.3](../../../plans/ui-prototype-v2/design-v2.md#53-双视角bad-case--进化对象): member rows show type/name/subdirectory; this issue adds the "name matching" switch and before/after evidence.
- Agent Note [Body hash by default, explicit switch for agent name matching](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/architecture/2026-11-26-agent-name-match-switch.md): the trade-offs of the previous deployment-level switch; this issue replaces it with member config and retires the env switch.
- Agent Note [Attribution identity as normalized body hash and the post-process anchor](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/architecture/2026-11-18-body-hash-attribution-post-process.md): body-hash identity and the existing "never guess a name" decision; the member switch remains a bounded, off-by-default exception.

## Prototype comparison

Same V2 prototype, same page state (`?u=admin&ws=ws-harness&page=overview&tab=targets`), 1500×1200 CSS viewport, 2× DPR, light theme; data is the synthetic `ws-harness` fixture. The scenario is the new-target dialog with one skill member and one agent member: the baseline has only type/name/subdirectory; the change adds a "name matching" switch to each member row, with skill off and agent on to show that the switch is per member.

| Before (`main` prototype, no switch) | After (#651 prototype, member-row switch) |
| --- | --- |
| [![Before: member rows only show type, name and subdirectory](https://github.com/Shadow-Azure/harness-evolution/releases/download/skill-name-match-prototype-evidence-20261127/skill-name-match-before.png)](https://github.com/Shadow-Azure/harness-evolution/releases/download/skill-name-match-prototype-evidence-20261127/skill-name-match-before.png) | [![After: skill off, agent on](https://github.com/Shadow-Azure/harness-evolution/releases/download/skill-name-match-prototype-evidence-20261127/skill-name-match-after.png)](https://github.com/Shadow-Azure/harness-evolution/releases/download/skill-name-match-prototype-evidence-20261127/skill-name-match-after.png) |

Both images share page, data, dialog structure, shared block and member type/name/subdirectory; the only difference is the new "name matching" switch at the end of each member row.

## Implementation

### Prototype and design (merged in #651)

- Add a `matchByName` argument and a fourth column switch to `v2TargetMemberRow` in `plans/ui-prototype-v2/harness-evolution.html`; the member grid becomes `type / name / subdirectory / name matching / remove`, reusing the existing `.switch` visual language at member-row size.
- `v2TargetModal` renders the existing member `matchByName`; `v2SaveTarget` writes `matchByName` back to the member object; the member hint mentions that each member decides its matching mode.
- Record the member-level switch default, semantics and location in `plans/ui-prototype-v2/design-v2.md §5.3`.
- Put before/after screenshots into this issue; the prototype PR ships no product code, database migration or contract field.

### Data model and contracts

- Add an Alembic migration (`0036_member_match_by_name.py`) adding `match_by_name` boolean, `NOT NULL DEFAULT false`, to both `evolution_target_members` and `evolution_run_targets`; no backfill to true. Do not add a deployment-level column to `evolution_targets`.
- Legacy targets without member rows synthesize a member with `match_by_name=false`, preserving today's behavior.
- Contracts: add `matchByName: bool = false` to `EvolutionTargetMemberWrite` and `EvolutionTargetMember`, and to the `EvolutionRunTarget` snapshot; run `pnpm contract:generate` to update OpenAPI and generated types.
- Persistence: carry the field through `EvolutionTargetMemberRecord`, `EvolutionRunTargetRecord`, repository member load/write, `_member_rows`, and run-target writes/reads; keep each member's own value on create/update.

### Matching and overview

- Add `match_by_name: bool = False` to `MatchTarget`; `MatchCondition` always carries member-level `targets`. `PotentialMatcher.associated_sessions` lets each target's switch decide whether to ignore revisions: on matches by type + name, off keeps the existing `observed_revisions` filter.
- Remove the service-level `agent_match_by_name` / `name_match_types` and `main.py` wiring; `TargetOverviewService` no longer takes a global switch and instead receives `match_by_name` from the member record through `_member_target`.
- `_analyse_target` uses `target.match_by_name` to choose the single version row or the existing `_build_version_labels`; `_name_matched_version` and `_name_match_aliases` become type-neutral and are shared by skill/agent.
- The name-mode row's aliases still cover configured ref, resolved revision, bare body hash and historical report `object_version`; `_newest_link_by_case` keeps the newest report per case so attributed/nonTarget counts never drop to zero.
- `launch.py`, `prepare.py` and `binding_worker.py` pass the member switch into `MatchTarget` and into the run member snapshot; wizard/launch currently pass no revision filter and remain presence-based, so their default behavior does not change. Carrying the switch in the snapshot means a later unification does not need another schema change.
- Knowledge members have no switch and always use `match_by_name=false`; skill/agent default to false.

### Frontend

- Add an `el-switch` labeled "name matching" to member rows in `apps/web/src/pages/evolution/targets/components/TargetFormDialog.vue`; render it only for skill/agent, default off for new members, and echo the saved value when editing.
- Add `matchByName: boolean` to `TargetMember` in `apps/web/src/pages/evolution/targets/targetMembers.ts`; preserve it on read/backfill/submit and treat a missing legacy value as false.
- Update the target API composable and submit payload, member unit tests and form tests; knowledge members render no switch.
- Do not add a separate settings page, move the switch into the shared block, or change the repository/baseline/test-project layout.

### Config cleanup and docs

- Remove `agent_match_by_name` from `apps/api/app/config.py`; remove `HE_AGENT_MATCH_BY_NAME` from `.env.example` and add no `HE_SKILL_MATCH_BY_NAME`; remove the related `main.py` wiring.
- Compatibility note: after upgrading, a deployment that set `HE_AGENT_MATCH_BY_NAME=true` starts with every member off and must enable members explicitly. Do not auto-backfill, which would silently merge same-name different-body objects. Write this into deployment docs and the release note.
- Change `docs/architecture.md` and its English pair from "agent name matching follows `HE_AGENT_MATCH_BY_NAME`" to "skill/agent members can explicitly match by name through `matchByName`, off by default, persisted with the member config"; run `pnpm record:i18n -- docs/architecture.md`.
- Update 05/06/07/08 for the member field, migration, `MatchTarget`/`MatchCondition`, frontend member row and overview behavior; add an Agent Note recording the "member switch replaces the env switch" trade-off, mark the previous agent-switch Note as superseded, and backfill the new Note path into `adr`.

## Implementation steps

1. Prototype and design (merged in #651): add the member-row switch, save/echo behavior, update `design-v2.md §5.3`, and put before/after screenshots into the issue; ship no product implementation.
2. Data and contracts: add the member/run-snapshot `match_by_name` migration, update `EvolutionTargetMemberWrite/Read`, `EvolutionRunTarget` and generated contracts; add migration and contract tests.
3. Persistence: carry the field through the members repository, target create/update and run-target snapshots; add repository/service tests.
4. Matching layer: add `MatchTarget.match_by_name`, `MatchCondition.targets` and per-member filtering in the matcher; remove the global switch and `main.py` wiring; add matcher tests for skill/agent/mixed members/knowledge.
5. Overview: pass the member switch through `_member_target`, let `_analyse_target` choose single-row vs multi-row per member, and keep name-mode aliases and historical reports; add overview API/unit tests.
6. Run path: carry the switch through launch/prepare/binding `MatchTarget`s and run snapshots so historical runs replay with the setting captured at creation.
7. Frontend: member-row switch, `TargetMember` type, payload, form and API tests; no switch for knowledge.
8. Remove `HE_AGENT_MATCH_BY_NAME`, update architecture/design docs and Agent Note, run API/Web/contract/E2E gates, and open the implementation PR with before/after UI evidence and the env migration note.

## Dependencies and boundary

- Dependencies: m13-01 (body-hash identity), m11-03 (overview API), m11-04 (overview UI); all are done. The same-repo multi-member model is already provided by the member model; this issue adds one member field and does not change that model.
- Prototype PR (#651) boundary: V2 prototype, `design-v2.md`, and this issue body and screenshots. It does not deliver the migration, API, frontend form, matcher or env cleanup.
- Later implementation boundary: one boolean on the member table and one on the run snapshot, contract fields, the member-form switch, and per-member matching branches. Do not change report identity, `targetRevision`, cache keys, step-4 statistics, event ingestion or parser algorithms.
- Name matching only applies when the switch is on; off keeps the existing body-hash rule. The current presence-based default of wizard/launch is not changed by this issue.
- Do not backfill historical data to true; users explicitly enable name matching per member in the new form.
- Backfill the new Agent Note into this issue's `adr` in the implementation PR; the prototype PR adds no decision record; #651 kept `adr` empty.

## Verification

Prototype PR (#651, merged):

```sh
pnpm verify:flow
pnpm verify:flow -- --diff origin/main
pnpm lint:docs
pnpm verify:docs
```

- Prototype: with the same fixture, 1500×1200 viewport, 2× DPR and light theme, the before member rows have no switch and the after skill/agent rows each have a "name matching" switch, with skill off and agent on; the screenshot links are in the issue.
- Prototype save: toggling a switch in the after prototype and saving, then reopening the editor, echoes that member's switch state; knowledge members render no switch.
- Issue: the body is rewritten from env variables to member-level `matchByName`, with data/contract/matching/frontend/cleanup/acceptance sections and no leftover "add `HE_SKILL_MATCH_BY_NAME`" instruction.
- Flow and docs: `pnpm verify:flow`, `pnpm verify:flow -- --diff origin/main`, `pnpm lint:docs` and `pnpm verify:docs` pass.

This implementation PR:

```sh
pnpm test:api -- tests/bugfix-skill-name-match tests/m10-02-potential-matcher tests/m11-03-target-overview
pnpm test:web -- target
pnpm lint:api
pnpm typecheck:api
pnpm typecheck:web
pnpm contract:check
pnpm test:e2e -- --pattern "target"
pnpm verify:flow
pnpm verify:docs
```

- Migration: existing members/runs get `match_by_name=false`; synthesized members are false.
- API: member create/read returns `matchByName`, default false; contracts are not hand-edited.
- Matching: only enabled members ignore revisions; disabled members stay hash-filtered; mixed configurations are independent; knowledge is unaffected.
- Runs: the run snapshot keeps the setting from creation, so later config edits do not change historical replay.
- UI: before/after screenshots of a member switch off/on with the same fixture, viewport and theme go into the implementation PR; knowledge members have no switch.

## Acceptance

1. The prototype member rows show a "name matching" switch for skill and agent independently, off by default; knowledge has none; this issue carries same-scenario, same-viewport, same-theme before/after screenshots.
2. The issue is rewritten as member-level `matchByName`, explicitly removes `HE_AGENT_MATCH_BY_NAME`, does not introduce `HE_SKILL_MATCH_BY_NAME`, and documents the env migration and default-false impact.
3. The prototype PR contained no product implementation (#651 satisfied); the implementation PR passes every gate.
4. After implementation: the member table and run snapshots persist `matchByName`; API contracts/generated types are updated; existing data defaults to false and synthesized members are false.
5. After implementation: a member with the switch off keeps body-hash matching; a member with it on matches by name in overview and association, shows a single version row, keeps historical report aliases and does not zero counts; other members in the same configuration are unaffected.
6. After implementation: the run snapshot keeps the switch from creation; later config edits only affect future matching and never rewrite historical reports or `targetRevision`.
7. After implementation: wizard/launch presence behavior is unchanged; report cache, step-4 statistics, event ingestion and parser algorithms are unchanged.
8. After implementation: the frontend member form can toggle and echo the switch, knowledge shows none; `pnpm contract:check`, API/Web/E2E gates pass; UI switch before/after screenshots are in the implementation PR.
9. Durable docs are updated and re-recorded in both languages; a new Agent Note records the member-level decision and `adr` is backfilled.

## Gates and CI

- Prototype PR (#651): `pnpm verify:flow`, `pnpm verify:flow -- --diff origin/main`, `pnpm lint:docs`, `pnpm verify:docs`; CI docs-flow, flow-online and the other lanes pass; no product API/Web tests because there is no product code.
- Implementation PR: API `pnpm lint:api`, `pnpm typecheck:api`, focused `pnpm test:api -- tests/bugfix-skill-name-match tests/m10-02-potential-matcher tests/m11-03-target-overview`; Web `pnpm lint:web`, `pnpm typecheck:web`, `pnpm test:web`; contracts `pnpm contract:generate` / `pnpm contract:check`; migration and DB tests; E2E target-configuration cases.
- Flow: commit and PR titles contain `(#N)`; this issue is in-progress; `pnpm verify:flow` and `pnpm verify:flow -- --diff origin/main` pass.
- UI-visible change: the implementation PR must carry same-fixture, same-viewport, same-theme before/after screenshots of the member switch off/on; the #651 prototype screenshots are design evidence only.
- Agent Note: the implementation PR adds the member-switch decision record and backfills `adr`; do not commit run logs, production Sessions or credentials.

## Non-goals

- The prototype PR does not implement the migration, API, frontend or matcher; this implementation PR delivers the product behavior.
- Do not keep or add any `.env` matching switch; no deployment-level default, env fallback or automatic backfill.
- Do not move report content identity, `targetRevision`, cache keys, frozen source or step-4 statistics from the body hash to the name.
- Do not change the current presence-based default of wizard/launch; if the three paths should be unified later, open a separate issue.
- Do not change knowledge matching or introduce a global "name first, hash fallback" automatic fallback.
- Do not change `TargetContentResolver`/`TargetDefinitions` read/error behavior or guess content from a name or default branch.
- Do not migrate, backfill or recompute historical version rows or reports; do not change event ingestion or parser algorithms; do not add a separate switch page or a second configuration page.
