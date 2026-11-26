# Add an opt-in .env switch for agent targets matched by name (default off)

English | [中文](bugfix-agent-name-match-toggle.md)

```yaml flow
kind: issue
id: bugfix-66
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
  number: 632
  url: https://github.com/Shadow-Azure/harness-evolution/issues/632
```

## Background

The requester wants an `.env` matching switch, off by default; when enabled, agent evolution targets should match by name instead of the definition body digest. The current implementation does give agents a normalized-body-hash identity rather than a name identity, but not every read path filters by it:

- Target version resolution reads `AGENT.md`/`agent.md` at the selected ref and derives `targetRevision=digest:<sha256(normalize_definition_body(body))>` through the frontmatter-aware `definition_file_hash` (`apps/api/app/service/evolution/target_content.py`). A failed read returns `TARGET_CONTENT_UNRESOLVED`; it never falls back to a name.
- An agent trigger event stores `object_revision=digest:sha256(agentType + builtin marker + body hash)` (the composed digest from `_agent_revision` in `apps/api/app/service/acquisition/parsers/base.py`), which differs from the pure body hash the target resolves; `definition_hash` carries the pure body hash.
- Wizard steps 2/3, the launch potential precheck and background binding call `PotentialMatcher.associated_sessions` without `observed_revisions`, so they already associate by object type plus name presence. The overview target analysis (right-hand target list, trend, case list and detail share `_analyse_target`) passes `condition.revision_candidates` (`apps/api/app/service/overview/targets.py`) and requires an event `object_revision`/`definition_hash` to hit that version's hash.
- The launch latest-reports cache gate, the step-4 reused/non-target statistics and background binding dedupe still query by `targetRevision` (`launch.py`'s `latest_reports` gate, the bound-package preview branch in `potential.py`, and `binding_worker.py` completion dedupe); they belong to the report/cache scope, not this switch's association layer.
- Consequently one agent name can appear as several digest rows in the overview: the configured ref's row filters down to zero Sessions by hash even though the same name exists in traces, and agent bodies drift across versions, trace snapshots and runtime-injected prompts. The overview and the wizard also disagree on the association rule.

Name matching deliberately groups same-name agents with different bodies into one object, giving up version precision. It must therefore be an explicit, configurable, default-off exception; the default stays body hash, and the existing "never guess a name for an unknown revision" decision is unchanged.

## Goals

- Add the optional environment variable `HE_AGENT_MATCH_BY_NAME`, boolean, default `false`, read once at API startup; changing it requires restarting `harness-api`.
- Off (default): behavior is byte-for-byte unchanged, including body-hash identity, overview version rows, error codes and existing tests.
- On: for `object_type=agent` targets only, Session association and overview version rows match by object type plus name and no longer filter on `definition_hash`/`object_revision`; one agent target shows one configured-version row (the target `defaultRef`) and counts every same-name Session.
- While on, historical attribution reports still attach to the same single agent row (newest report per case); the version collapse does not make them disappear or zero their counts.
- Report content identity, `targetRevision`, prompt freezing, run snapshots, cache keys and step-4 statistics keep using the body hash; the switch changes only the association/version-row matching layer, not report bodies or cache scope.
- Skill and knowledge targets are unaffected; event ingestion, database schema and the OpenAPI contract stay unchanged.
- Historical digest versions and reports remain readable; no backfill or rewriting.

## Design authority

- [05 §4.20 Evolution preview and launch (V2)](../../../plans/fullstack-design/05-api-design.md#420-自进化预览与启动v2): `targetRevision` only fixes the source text, reports and cache scope, while Session association follows object type and name presence; this switch extends that rule to the overview version rows that still filter by hash.
- [05 §4.18 Overview and workspace Session lists (V2)](../../../plans/fullstack-design/05-api-design.md#418-总览与空间-session-列表v2): the object-card version identity and `byVersion` contract; when on, an agent version key becomes the single configured ref.
- [06 §5.1 evolution_targets](../../../plans/fullstack-design/06-database-design.md#51-evolution_targets--可自进化的对象配置): target type, `defaultRef` and binding fields; the switch adds no columns.
- [06 §7.5 V2 semantics](../../../plans/fullstack-design/06-database-design.md#75-v2-口径空间--触发点--潜在--归因三态): object occurrence and entry points, potential and attribution.
- [07 §5.12 Potential matching](../../../plans/fullstack-design/07-backend-implementation.md#512-潜在匹配serviceevolutionpotentialpy): the query and filter sites inside `PotentialMatcher`.
- [08 §9.5 Evolution target configuration page](../../../plans/fullstack-design/08-frontend-implementation.md#95-进化对象配置页evolutiontargets): object version and overview entry points; this issue adds no form fields.
- Agent Notes [normalized body hash identity and post-process anchors](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/architecture/2026-11-18-body-hash-attribution-post-process.en.md) and [Claude subagent prompt resolution](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/bug-fix/2026-11-21-claude-attachment-prompt-snapshot.en.md): the body-hash identity decision and the reason name-only matching was rejected then; this switch is a bounded, default-off exception.

## Implementation

### Configuration

- Add `agent_match_by_name: bool = False` to `Settings` in `apps/api/app/config.py`, read through the `HE_` prefix; an invalid boolean fails at startup through the existing Pydantic validation.
- Add `# HE_AGENT_MATCH_BY_NAME=false` to `.env.example` near the attribution/self-evolution options (`HE_ATTRIBUTION_*`), stating that it only affects agent-target association and overview version rows, is off by default, and needs an `harness-api` restart.

### Shared matcher

- Add an `agent_match_by_name` constructor argument to `PotentialMatcher` (default `False`); pass `resolved_settings.agent_match_by_name` at both construction sites in `apps/api/app/main.py`.
- In `associated_sessions`, ignore the supplied `observed_revisions` when the switch is on and `condition.target_type == "agent"`; every other branch, count and ordering stays unchanged.
- Wizard steps 2/3 and the launch potential precheck already skip the revision filter; they need no code change, but a regression assertion must prove they behave identically with the switch on.
- `latest_reports`, `count_non_target_cases`, the step-4 bound-package preview and `BindingWorker` completion dedupe stay as they are (the report scope still keys on `targetRevision`) and are outside this switch's change surface.

### Target overview detail

- Give `TargetOverviewService` the same switch; with it on and an agent target, do not accumulate digest versions from event `object_revision` via `_build_version_labels`; build one canonical version whose key and display are the target `defaultRef`.
- That version does not pass `observed_revisions` and associates every Session in the window that contains the agent name; event versions stay as evidence but do not decide inclusion.
- Historical reports must still attach to that row, but `_newest_link_by_case` selects a report only when its `object_version` is in the label aliases, and a single-ref version has no historical digest aliases. Name mode must build that row's alias set (configured ref, resolved revision, bare hash, and the object's historical report `object_version` values) or equivalently pick the newest report per case for the object, so existing attributed/nonTarget counts do not drop to zero. Filtering `list_attributions` by object alone is not enough.
- `byVersion` has one row and the response fields neither grow nor shrink; historical digest versions participate as aliases for report matching and are not shown as separate version rows.
- Content resolution still feeds the displayed ref/commit and the launch path; a resolution failure no longer turns the row into "unresolved, zero Sessions" because matching is by name. Launch still requires content and keeps returning the existing `TARGET_CONTENT_UNRESOLVED`.
- Skill/knowledge targets keep the existing `_build_version_labels` path; the switch is a no-op for them.

### Documentation and decisions

- Add one sentence to `docs/architecture.md` and its English pair next to "never guess a name": agent name matching is an explicit exception controlled by `HE_AGENT_MATCH_BY_NAME`, off by default.
- Update design sections 05/06/07/08 with the conditional semantics: default hash; when on, agent association/version rows use the name while reports and caches still key on the body hash.
- Add an Agent Note (under `implemented/architecture` or `implemented/feature`) recording the trade-off "default hash, explicit switch opens agent name matching" and the "report content identity is unchanged" boundary, and backfill its path into this issue's `adr`.

## Implementation steps

1. Add the `Settings` field and unit tests (unset, false, true, invalid), and update `.env.example`.
2. Add the switch to `PotentialMatcher`, branch `associated_sessions`, and add matcher tests.
3. Change the agent name-mode version building, association and historical report aliases in `TargetOverviewService`; add overview API/unit tests: off keeps the existing digest rows; on yields one row that includes same-name Sessions whose hash does not match, while existing attributed/nonTarget counts stay non-zero.
4. Update `docs/architecture` in both languages and design sections 05/06/07/08, add the Agent Note, and run the document and pairing gates.
5. With fixtures, call the overview detail locally with the switch off and on, recording version-row count, associated Session count, historical report attachment and `byVersion`; if browser rendering is involved, attach same-fixture, same-viewport, same-theme before/after screenshots.
6. Run this issue's verification commands, commit and open a PR whose description shows the default-off compatibility evidence and the on-behaviour comparison.

## Dependencies and boundary

- Depends on m13-01 (body-hash identity), m11-03 (overview API) and m11-04 (overview UI); all are done.
- Delivery boundary: one environment variable, the shared matcher's filter, overview version aggregation and historical report aliases; no schema, OpenAPI, ingestion, `targetRevision`, report-cache-key or step-4 statistics change.
- Do not change `TargetContentResolver`/`TargetDefinitions`: `AGENT.md` stays required content for launch and attribution, read failures stay explicit, and no name guessing supplies a body.
- Do not rewrite historical rows, migrate, or recompute historical reports; the switch can be turned back off at any time to restore hash semantics.

## Verification

```sh
pnpm test:api -- tests/m11-03-target-overview tests/m10-02-potential-matcher tests/m13-01-body-hash-attribution
pnpm lint:api
pnpm typecheck:api
pnpm verify:flow
pnpm verify:docs
```

- Config tests: unset/false means off; true means on; an invalid value fails startup validation.
- Matcher and overview tests: off keeps existing digest version rows and counts; on gives an agent target one row and includes same-name Sessions with a different definition hash; a skill target keeps digest rows with the switch on.
- Overview reports: with the switch on, cases that only have historical digest reports still attach to the single version row, and attributed/nonTarget counts match the switch-off result instead of dropping to zero because aliases are missing.
- Document gates: `docs/architecture` is re-recorded in both languages; `pnpm verify:docs` and `pnpm verify:flow` pass.
- Browser check: with the same fixture, viewport and theme, off shows the existing digest version rows and on shows only the configured-ref row; screenshots go into the PR description.

## Acceptance

1. With `HE_AGENT_MATCH_BY_NAME` unset or `false`, overview version rows, association counts, step-4 statistics and error codes are byte-for-byte identical and existing tests need no assertion changes.
2. With `HE_AGENT_MATCH_BY_NAME=true` and an API restart, an agent target detail has one configured-version row; same-name Sessions count even when their `definition_hash` differs from the target body hash, and same-name digest rows no longer appear.
3. Under the same switch, skill and knowledge targets are unchanged; a mixed workspace (skill + agent targets) is unaffected across types.
4. With the switch on, historical reports still attach per case to the single version row and attributed/nonTarget counts do not drop to zero through the version collapse or missing aliases; step-4 `reused/fresh` and `nonTargetKnown` still follow the body-hash report scope, and report bodies, `targetRevision` and run snapshots are not rewritten.
5. Turning the switch off restores hash semantics; historical digest versions and reports remain readable without a data migration.
6. When `AGENT.md` is missing or unreadable, launch/attribution still return the existing `TARGET_CONTENT_UNRESOLVED`; name matching never bypasses the content read.
7. Resident documents are updated in both languages with re-recorded pairing; the Agent Note records the switch trade-off and the `adr` is backfilled.

## Gates and CI

- API: `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test:api -- tests/m11-03-target-overview tests/m10-02-potential-matcher tests/m13-01-body-hash-attribution`.
- Contract: with no DTO change, `pnpm contract:check` must show no diff; if the implementation unexpectedly touches a DTO, update design 05 and regenerate first.
- Docs: `pnpm lint:docs`, `pnpm verify:docs`; after changing `docs/architecture` in both languages run `pnpm record:i18n -- docs/architecture.md`.
- Flow: commits and the PR title carry `(#N)`; move this issue to in-progress before opening the implementation PR; `pnpm verify:flow` and `pnpm verify:flow -- --diff origin/main` pass.
- Visible UI change: the PR description carries same-fixture, same-viewport, same-theme before/after screenshots for the switch off and on; after-only evidence does not count as done.

## Non-goals

- Do not switch agent `targetRevision`, report cache keys, prompt freezing or step-4 statistics from body hash to name; reports for same-name different bodies must still be separated by content.
- Do not change `TargetContentResolver`/`TargetDefinitions` reads or errors; do not guess a body from the name or the default branch.
- Do not change skill or knowledge matching; do not add a global "name first, hash fallback" automatic fallback; do not change the scope of `latest_reports`, `count_non_target_cases` or background binding dedupe.
- Do not add a UI toggle, form field or contract field; do not change deployment injection; production configures the server `.env` and restarts.
- Do not migrate, backfill or recompute historical version rows and reports.
