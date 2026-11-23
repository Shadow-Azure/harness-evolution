# Make object presence the single attribution contract and remove stale docs/prototype behavior

English | [中文](bugfix-attribution-presence-single-source.md)

```yaml flow
kind: issue
id: bugfix-43
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - .agents/flow/issues/bugfix-attribution-presence-single-source*
  - .agents/flow/issues/bugfix-ignore-image-files*
  - .agents/notes/implemented/architecture/2026-11-17-potential-matcher*
  - plans/ui-prototype-v2/harness-evolution.html
  - plans/fullstack-design/02-features.md
  - plans/fullstack-design/05-api-design.md
  - plans/fullstack-design/06-database-design.md
  - plans/fullstack-design/07-backend-implementation.md
  - plans/fullstack-design/08-frontend-implementation.md
  - plans/fullstack-design/README.md
  - plans/2026-11-23-pr421-plans-review.md
  - apps/api/tests/m10-02-potential-matcher/test_preview_api.py
adr:
  - ../../notes/implemented/architecture/2026-11-17-potential-matcher.md
github:
  number: 554
  url: https://github.com/Shadow-Azure/harness-evolution/issues/554
```

## Background

PR #421 changed Session association from exact target-version matching to object presence: any trigger with the selected type and name anywhere in the Session tree qualifies. It also added target-bound Skills, background reports, and latest-report reuse per object and version. Production already runs with presence, and `test_unknown_and_nonmatching_revisions_are_associated` locks the behavior for missing and different revisions.

The delivery only updated half of the surface. 05/06/07/08 still say "identity match", "no name-level guessing", or "cache_key / rule-v1"; target binding fields, Skill package tables, and migrations 0023a–0031 never reached the 05/06 contracts; the prototype writes the step-4 recompute Skill into `EV_STATE.wz.attributionSkill` but never carries it into the Run, while Run detail still uses the old `m.reused / m.fresh` and cache-key text. The result is two concurrent truths for the same behavior.

## Goals

- Make **type + name presence** the only Session-association contract; `targetRevision` only fixes source content, reports, and cache scope. `versionUnresolved` is a compatibility field that is always zero for new batches.
- Add target-bound Skills, workspace Skill packages, V2 report fields, and migrations 0023a–0031 to the 05/06 contracts.
- Remove stale exact-version statements from 05/06/07/08/02/README; when legacy rule keeps `cache_key / rule-v1`, label it explicitly as a compatibility path.
- Fix the prototype data flow: the step-4 Skill reaches the Run and remains traceable; step 4 and Run detail share the same reuse/fresh/missing counts; cache-on with zero reports disables launch; existing reports group by source Skill.
- Add an API regression test proving sessions with missing and different versions both enter `preview/sessions` with `versionUnresolved=0`.

## Design authority

- [05 §4.9 / §4.11 / §4.20](../../../plans/fullstack-design/05-api-design.md): preview, target CRUD, attribution preview contracts.
- [06 §4.2.2 / §5.1 / §5.8 / §7.5 / §9](../../../plans/fullstack-design/06-database-design.md): report fields, target columns, write semantics, association contract, migrations.
- [07 §5.12–5.14](../../../plans/fullstack-design/07-backend-implementation.md): matcher, attribution generation, preview endpoints.
- [08 §9.2 / §9.5 / §10](../../../plans/fullstack-design/08-frontend-implementation.md): wizard, target form, run detail.
- [02 object-bound attribution](../../../plans/fullstack-design/02-features.md#对象绑定归因): feature narrative and acceptance summary.
- [PotentialMatcher decision](../../notes/implemented/architecture/2026-11-17-potential-matcher.en.md): the single presence implementation and its rationale.

## Implementation

- **05**: add `bySkill/missing` to `stats` and `preview/attribution`; add nullable `attributionPackageId` to target CRUD plus Skill package list/upload/detail/download/delete APIs; split "association and cache use targetRevision" into presence association and targetRevision cache scope; replace "matching accepts body hash" with type+name association.
- **06**: add `attribution_package_id / attribution_generation / attribution_snapshot` to `evolution_targets`; document `attribution_skill_packages` and `attribution_skill_package_bindings`; add V2 report columns (`report_schema_version / report_payload / execution_manifest / execution_manifest_hash / attribution_skill_name / analyzed_at / binding_generation`); make §7.5 presence-only and isolate legacy `cache_key`; add migrations 0023a–0031.
- **07**: make "trigger identity" describe target content resolution only; split bound-package latest reports from legacy cache_key; change `preview/sessions` to presence and `preview/attribution` to latest reports with `bySkill/missing`; add package/binding ownership.
- **08**: remove body-hash matching from step 2; keep the new step-4 stats and zero-hit launch guard; change run-detail "four counts" to potential/attributed/non-target/reused/missing/fresh and show the Run's Skill; add the attribution Skill field to the target form and document the Skill resource page; keep legacy inline prompts read-only.
- **02 / README**: update F26 item 4; restore date, rationale, and 05/06/07 links in D23 without overwriting traceability.
- **Prototype**: pass `attributionSkill` through `evMakeRun` / `evWzRun` / `ev-wz-start`; unify `hasReport / reused / fresh / missing`; share counts between step 4 and Run detail and group by source Skill; disable launch when cache is on and zero reports exist; preserve read-only legacy inline binding in target editing.
- **Tests**: add a `test_preview_api.py` case where one session has a different version and one has no version; assert `summary.associated=2` and `versionUnresolved=0`.
- **Note**: update `2026-11-17-potential-matcher` with the consequence that docs and prototype must not reintroduce version-exact association.

## Implementation steps

1. Create the issue, sync its GitHub number, and move it to in-progress.
2. Update docs in order 05 → 06 → 07 → 08 → 02/README: settle the contract first, then add fields.
3. Update the prototype data flow, counts, and Skill grouping; verify in headless Chrome.
4. Add the `test_preview_api.py` regression and update the owning Note (English side and pairing record).
5. Run docs, flow, gates, and focused API tests; commit, open a PR, and merge after CI.

## Dependencies and boundary

- Dependencies: none.
- Only docs, prototype, flow files, tests, and the Agent Note change. Do not change the production matcher, database schema, generated OpenAPI, or production Vue components.
- Production already runs presence. This issue does not restore exact-version matching or make legacy inline prompts editable again.

## Verification

```sh
pnpm test:api -- tests/m10-02-potential-matcher/test_preview_api.py tests/m10-02-potential-matcher/test_matcher.py
pnpm lint:docs
pnpm verify:docs
pnpm verify:flow
pnpm test:gates
```

- Focused API tests pass; the new case returns two associated sessions with `versionUnresolved=0`.
- All four docs/flow gates pass.
- Prototype check: with cache off, select `harness-trace-review` and launch; the Run object carries `attributionSkill=harness-trace-review`. Step 4 and Run detail show identical reuse/fresh/missing counts. With cache on and no candidate reports, the launch button is `disabled`.

## Acceptance

- 05/06/07/08 no longer state that Session association uses targetRevision or identity matching; `versionUnresolved` appears only as a historical compatibility field.
- 05 §4.11 documents `attributionPackageId` and the workspace Skill package APIs; 06 §5.1 has the three binding columns and both package tables; §9 summarizes migrations 0023a–0031.
- F26, 08 §10.1, and Run detail no longer say "four counts"; README D23 keeps its date and 05/06/07 links.
- Prototype: the selected Skill is traceable in the Run; step 4 and Run detail agree; zero-report cache-on disables launch; existing reports group by source Skill.
- The API regression passes; repository gates pass; after merge, `main` no longer contains the stale statements listed here.

## Gates and CI

- `pnpm test:api -- tests/m10-02-potential-matcher/test_preview_api.py tests/m10-02-potential-matcher/test_matcher.py`
- `pnpm lint:docs`, `pnpm verify:docs`, `pnpm verify:flow`, `pnpm test:gates`
- Commit and PR titles carry `(#N)`; the PR description lists docs/prototype evidence.

## Non-goals

- Do not change `PotentialMatcher.associated_sessions` presence behavior or restore exact-version matching.
- Do not change database schema, migrations, generated OpenAPI, or production Vue components.
- Do not add Skill upload protocols, intranet Agent integration, or clustering/evaluation changes.
- Do not make legacy inline prompts editable again; keep read-only history only.
