# Multiple skills or agents in one repository as one evolution target

English | [中文](bugfix-68-multi-member-evolution-target.md)

```yaml flow
kind: issue
id: bugfix-68
milestone: bugfix
depends:
  - m5-02
  - m10-02
  - m12-03
priority: P2
status: done
scope:
  - apps/api/alembic/**
  - apps/api/app/db/**
  - apps/api/app/errors.py
  - apps/api/app/service/**
  - apps/api/app/api/**
  - apps/api/app/third_party_api/**
  - apps/api/tests/**
  - apps/web/src/**
  - packages/contracts/**
  - tests/e2e/**
  - plans/**
  - scripts/doc-budgets.manifest.json
  - .agents/**
adr: []
github:
  number: 640
  url: https://github.com/Shadow-Azure/harness-evolution/issues/640
```

## Background

### Problem

One repository often holds several skills and agents at once, for example `skills/deep-research` and `skills/code-review`: they share the repository, baseline, and evaluation projects, and their bad cases often come from the same sessions. Today one `evolution_targets` row carries a single object — the unique constraint is `(workspace_id, object_type, object_name)`, and the scope `sub_dir`, the validation/test project IDs, and the binding attribution all hang off that row. Configuring such a group as one evolution target can only be done as N configurations, so:

- the repository, baseline, test project IDs, primary metric, and attribution Skill are filled N times;
- bad-case ownership is scattered across N configurations, so the group cannot be filtered or attributed as one target;
- one run can only target one object and cannot use the fact that these cases usually involve several objects;
- the patch may change only one directory and the evaluation submits only one asset.

### Requirements

- **Configure once**: repository URL, baseline branch or tag, validation/test project IDs, primary metric key, and attribution Skill are filled once per evolution target; enabling or disabling is not a form switch and is controlled by the "disabled" group in the overview (consistent with #628 in this repository).
- **List members**: each member has a type (skill / agent), a name, and a sub-directory; members share the configuration above but freeze their own definitions and associate their own bad cases.
- **Evolve the group in one run**: one baseline commit, a patch scope covering every member directory, one evaluation submitting all member assets, and member identities visible in commit messages and the seven steps.
- **Read the overview per configuration**: one row per configuration with the overall potential bad cases and associated sessions; members appear as chips and detail, and the case table marks the hit member.
- **Stay compatible**: historical configurations are backfilled as single-member configurations; historical runs without a member snapshot read the legacy columns; V1 read endpoints keep their semantics during the compatibility window.

### Discussion and decision

The 2026-11-26 discussion first prototyped "one configuration per member plus a multi-select wizard", which review rejected: duplicated configuration, scattered bad-case ownership, and an artificial "primary object". Three shapes were then compared:

| Shape | Description | Decision |
|---|---|---|
| A | One configuration = one evolution target holding several members from the same repository | **Adopted** |
| B | One configuration per member, with a multi-select wizard | Rejected: duplicated configuration, scattered ownership, "primary object" |
| C | Batch form filling only, one object per run | Rejected: does not evolve the group |

Three boundaries follow:

- **Shared**: repository, baseline, validation/test project IDs, primary metric, and attribution Skill; the enabled state is controlled by the "disabled" group in the overview and is not part of the configuration form.
- **Member**: type, name, sub-directory, definition snapshot (commit / digest / body).
- **Two hard constraints**: members must share the repository (one run has one `base_commit`); a member belongs to exactly one configuration (otherwise bad cases and attribution reports become ambiguous). The wizard therefore goes back to a single selection and has no "primary object".

The external contract is verified: in `ai-eval-platform@main d5231fe`, `asset_override.asset_paths` is a `list[str]` with no count cap, whole-field replacement, one commit per launch, and a single 422 when any path is missing; the test projects and primary metric are therefore shared, matching the platform's one-template-per-launch constraint.

### Prototype screenshots

Screenshots are kept locally only and are not distributed with the repository (`.gitignore` ignores every image format). The four target-state pages:

- **Configuration**: a shared block (repository / baseline / validation and test project IDs / primary metric / attribution Skill) plus editable member rows.
- **Launch wizard**: one configuration is selected, members are read-only, and the version plus test projects are shared.
- **Run detail**: the configuration name, member chips, shared test projects, and the change scope.
- **Workspace**: the change scope lists one glob per member directory.

Reproduce locally by opening `plans/ui-prototype-v2/harness-evolution.html` (`?u=admin&page=overview&tab=targets`, `?demo=wizard1`, `?demo=run`) or by running `capture.mjs before|after`; the before state and the explanation are in [18 §6.5](../../../plans/fullstack-design/18-multi-member-evolution-target.md#65-原型截图).

## Goals

- One configuration saves several skills or agents from the same repository and produces exactly one `evolution_targets` row plus N `evolution_target_members` rows.
- Save-time validation covers member names, sub-directories, test project IDs, and the primary metric; duplicate members and members owned by another configuration are rejected.
- Binding attribution runs once per configuration: a session containing any member is associated, and each case is attributed to its own object; a single-member configuration keeps the exact pre-change cache key.
- One run snapshots the member list; the patch scope and evaluation assets cover every member directory; a missing member directory fails prepare.
- Configuration, list, wizard, run detail, and overview present the two levels "configuration plus member", and the wizard returns to a single configuration selection.
- Historical configurations are backfilled as single-member configurations, and historical runs plus V1 read endpoints stay compatible.

## Design authority

- [18 §1 Background and decision](../../../plans/fullstack-design/18-multi-member-evolution-target.md#1-背景与决策): requirements, the three shapes, and the shared/member boundary.
- [18 §2 Domain model](../../../plans/fullstack-design/18-multi-member-evolution-target.md#2-领域模型) and [18 §3 Data model](../../../plans/fullstack-design/18-multi-member-evolution-target.md#3-数据模型): the two new tables, indexes, migration backfill, and legacy-column compatibility.
- [18 §4 API contract](../../../plans/fullstack-design/18-multi-member-evolution-target.md#4-api-契约): target CRUD, catalog, launch, and run projection requests and responses.
- [18 §5 Backend flow](../../../plans/fullstack-design/18-multi-member-evolution-target.md#5-后端流程): save, binding, launch, prepare, patch, evaluation, and final state.
- [18 §6 Frontend design](../../../plans/fullstack-design/18-multi-member-evolution-target.md#6-前端设计): the four screens and components, request mapping, and prototype screenshots.
- [06 Database design](../../../plans/fullstack-design/06-database-design.md): dialect-neutral storage, migrations, and naming.
- [05 API design](../../../plans/fullstack-design/05-api-design.md) and [07 Backend implementation](../../../plans/fullstack-design/07-backend-implementation.md): routing, service, and repository layering.
- [08 Frontend implementation](../../../plans/fullstack-design/08-frontend-implementation.md): page components and data flow.

## Implementation

- `apps/api/app/db/models/domain.py`, `db/models/evolution.py`: add `evolution_target_members` and `evolution_run_targets`; add `object_type / object_name / object_revision` to `evolution_run_candidates`; make the legacy `evolution_targets` columns nullable.
- `apps/api/alembic/versions/0035_*.py`: create tables and indexes, backfill members and run members, in both dialects.
- `apps/api/app/db/crud/evolution_targets.py`: records carry `members`, insert/update write members in one transaction, `find` joins the member table, delete cascades.
- `apps/api/app/service/evolution/targets.py`: the write model carries `members`, validates members and enforces global uniqueness, runs `ls-remote` once, and freezes each member's definition; `enabled_config_by_id` and `enabled_config_for_object` become the two entry points.
- `apps/api/app/service/evolution/binding_worker.py`, `attribution.py`, `attribution_context.py`: one batch per configuration, member snapshots, a `targets[]` context, and a byte-identical cache key for single members.
- `apps/api/app/service/evolution/potential.py`, `launch.py`, `prepare.py`: `MatchCondition(targets[])`, launch by configuration, member snapshots, and union matching.
- `apps/api/app/service/evolution/patch_source.py`, `git_candidate.py`, `third_party_api/git/workspace.py`: multi-directory `allowed_paths`, member-aware prompt, commit subject, and per-member `cat-file` preflight.
- `apps/api/app/service/evolution/engine/contracts.py`, `eval_poller.py`, `third_party_api/eval_gateway/ai_eval_platform.py`: `EvalRequest.targets[]` and one multi-asset submission.
- `apps/api/app/service/evolution/runs.py`, `stages.py`, `apply_final.py`, `service/overview/targets.py`, `service/catalogs.py`: two-level projection and aggregation for configuration and members.
- `packages/contracts`: regenerate OpenAPI and types.
- `apps/web`: configuration dialog with a shared block and member rows, configuration list, wizard with a single configuration and a read-only member panel, run detail, overview, and the member column in the case table.
- `plans/ui-prototype-v2`: prototype, capture script, and screenshots.
- `plans/fullstack-design/18-multi-member-evolution-target.md`: the design chapter.

## Implementation steps

1. Data layer: create the two tables plus the three candidate columns, backfill, and make the repository configuration-plus-member aware.
2. Configuration service: write model with members, validation and global uniqueness, one `ls-remote`, and per-member definition freezing.
3. Binding attribution: one batch per configuration, member snapshots, and a compatible context and cache key.
4. Launch and prepare: `MatchCondition(targets[])`, launch by `targetId`, run member snapshots, and per-member `cat-file`.
5. Patch and evaluation: multi-directory `allowed_paths`, commit subject, `EvalRequest.targets[]`, and the platform's multi-asset submission.
6. Projection and frontend: run detail, seven steps, overview, configuration page, and wizard; regenerate contracts.
7. Tests and documentation: unit, contract, E2E, fixtures, Agent Note, and architecture plus compatibility updates.

## Dependencies and boundary

- Dependencies: `m5-02` (target configuration API), `m10-02` (potential matching), and `m12-03` (real patch and evaluation).
- Boundary: only the same-repository multi-member configuration, binding, launch, patch, evaluation, and presentation; the platform asset contract is unchanged, cross-repository members are unsupported, and a member cannot belong to several configurations.
- Compatibility: the legacy columns are written with the first member for one release; historical runs without member rows fall back to the legacy columns; V1 read endpoints keep their semantics; tightening or dropping the legacy columns is deferred to the next release.

## Verification

```sh
pnpm test:api
pnpm test:web
pnpm typecheck
pnpm typecheck:web
pnpm contract:check
pnpm test:e2e --pattern m5-target-config
pnpm test:e2e --pattern m10-06
pnpm verify:flow
pnpm verify:docs
```

- Expected: member CRUD, global uniqueness, cascade delete, backfill, and legacy-run fallback tests pass; a single-member cache key is byte-identical to the pre-change key; the E2E case "one configuration, two members, one run" passes; contract and documentation gates are green.

## Acceptance

- One configuration saves two members from the same repository; duplicate members and members owned by another configuration are rejected and the error points at the member field.
- The wizard selects a configuration only; run detail shows members, sub-directories, shared test projects, and the change scope; steps 2 and 3 show the hit member.
- Binding attribution runs once per configuration; any member hit associates the session; each case is attributed to its own object; a single-member cache key is byte-identical.
- One evaluation submits all member assets; when a member directory is missing, prepare fails with `stage="subdirectory"`.
- Historical configurations are backfilled as single-member configurations; historical runs and V1 read endpoints behave as before.
- Prototype screenshots, the design chapter, and the Agent Note land in the same PR, and the flow and documentation gates pass.

## Gates and CI

- `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test:api`, `pnpm test`, `pnpm typecheck:web`, `pnpm contract:check`, `pnpm test:e2e`, `pnpm verify:flow`, `pnpm verify:docs`.
- Commits and the PR title carry the GitHub number; the implementation PR diff must stay within this issue's scope.

## Non-goals

- Do not change the evaluation platform's asset contract or error codes.
- Do not support cross-repository members and do not upgrade the run model to multi-repository, multi-commit.
- Do not allow one member to belong to several configurations.
- Do not change the attribution Skill executor, prompt protocol, or cache-policy version.
- Do not change the read-only mapping of the V1 six-step cursor or the semantics of V1 endpoints.
- Do not do "one test project per member" or "one evaluation per member".
