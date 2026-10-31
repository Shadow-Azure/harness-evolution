# Target configuration: add validation and test project IDs

English | [中文](m6-target-project-ids.md)

```yaml flow
kind: issue
id: m6-20
milestone: m6
depends:
  - m5-02
  - m5-03
priority: P1
status: ready
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - fixtures/**
  - tests/**
  - plans/**
  - docs/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 187
  url: https://github.com/Shadow-Azure/harness-evolution/issues/187
```

## Background

### What the problem is

`evolution_targets` currently stores only the object type, object name, repository URL, subdirectory, baseline branch or tag, and enabled state, and the create and edit dialogs expose only those five input groups. The validation set and the test set are hosted by two separate test projects on the external test platform, but the configuration has no field to record either project ID, so administrators cannot express which validation project and which test project an object uses.

### Symptoms

- The create dialog has no validation-set test project ID or test-set test project ID input.
- The `GET /api/evolution/targets` response, the `POST` and `PUT` request bodies, and the `evolution_targets` table have no matching fields.
- Different skills and agents can only share an implicit convention; the configuration layer cannot distinguish the validation and test projects.
- A later evaluation integration that selects a test project per object has no persisted source to read.

### Impact

- The configuration is incomplete, so the evaluation side cannot obtain a test project identity from the target configuration.
- Administrators can only record project IDs in documents or verbal agreements; the configuration page is not the source of truth.
- A later evaluation integration would need another table, API, and form change, which increases rework.

### Root cause

- `EvolutionTargetWrite` and `EvolutionTarget` declare only six fields, and `EvolutionTargetRecord` plus the repository insert/update paths read and write only six columns.
- The `evolution_targets` table has no project ID columns, and the migration chain stops at 0012.
- The frontend `TargetFormDialog` form model, required-field validation, reset, and emit cover only the existing fields, and `Index.vue` `targetWrite` copies only the existing fields.
- The contract is generated from FastAPI OpenAPI; without a backend model change, no new field appears in the frontend types.

### Recommendation

- Add `validation_project_id` and `test_project_id` columns to `evolution_targets` as `VARCHAR(128) NOT NULL`, backfilling historical rows with an empty string during migration.
- Make both fields required on write: non-empty after trimming, at most 128 characters, and free of control characters and whitespace; return a new `422 PROJECT_ID_INVALID` with `field` and `reason` in `details`.
- Add two required inputs to the create and edit dialogs with the same validation as the backend; populate saved values in edit mode and tell users to fill historical empty values before saving.
- Return both fields from the list endpoint; leave `GET /catalogs/targets`, the launch wizard, and the evaluation path unchanged in this slice.
- Update the contract, fixtures, migration, unit tests, E2E, prototype, and design documentation.

## Goals

- The create dialog contains two required fields, “validation-set test project ID” and “test-set test project ID”, for both skill and agent.
- The edit dialog populates and allows changing both fields; historical rows with an empty string render empty and require input.
- `POST` and `PUT /api/evolution/targets` accept and persist both fields, and `GET /api/evolution/targets` returns them.
- The `evolution_targets` table has both columns, and SQLite and MySQL migrations agree.
- Empty, whitespace-only, overlong, control-bearing, or whitespace-bearing input is rejected by both the frontend and the backend with a field-level message.
- The contract, fixtures, prototype, and tests stay in sync; existing target CRUD and repository validation behavior does not change.

## Design authority

- [05 §4.11 Evolution target configuration](../../../plans/fullstack-design/05-api-design.md#411-进化对象配置仅配置后可自进化): target configuration endpoints, fields, and error codes; this issue adds two fields to the body and response.
- [06 §5.1 evolution_targets](../../../plans/fullstack-design/06-database-design.md#51-evolution_targets--可自进化的对象配置): existing columns, constraints, and the run snapshot boundary; this issue only extends the table and does not change run snapshots.
- [08 §9.5 Target configuration page](../../../plans/fullstack-design/08-frontend-implementation.md#95-进化对象配置页evolutiontargets): form structure, required-field validation, and error presentation.
- [02 F19](../../../plans/fullstack-design/02-features.md): capability boundary of target configuration.
- The design document `plans/fullstack-design/14-target-project-ids.md` is completed before implementation and takes precedence on conflict.
- If implementation conflicts, the current `EvolutionTargetService` normalization and error wrapping take precedence.

## Implementation

- Database: add migration `0013_target_project_ids.py` with `validation_project_id` and `test_project_id` (`VARCHAR(128)`, `NOT NULL DEFAULT ''`) on `evolution_targets`; mirror the columns in `domain.py`.
- Backend: add `validation_project_id` and `test_project_id` to `EvolutionTargetWrite` and `EvolutionTarget`; map both columns in `EvolutionTargetRecord` and the repository insert/update/get/list paths; normalize and validate both fields in `_normalize_write`.
- Validation: non-empty after trimming, at most 128 characters, and no whitespace or control characters. Failures raise `AppError(422, PROJECT_ID_INVALID, "test project id is invalid")` with `field` (`validationProjectId` or `testProjectId`) and `reason` (`project_id_required` or `project_id_format`) in `details`.
- Error code: add `PROJECT_ID_INVALID` to `ErrorCode` and update the OpenAPI error response description.
- Contract: run `pnpm contract:generate` and update `packages/contracts/openapi.json` plus the generated types.
- Frontend: add two `ElInput` controls to `TargetFormDialog.vue` after the subdirectory/baseline row and before the enabled switch, in a two-column layout; cover the form model, reset, required-field validation, field errors, and emit; update `targetWrite` and `targetErrorMessage` in `Index.vue`.
- Form copy: explain that the validation set and test set map to test project IDs on the external test platform; when a historical row is empty, say the values must be filled before saving.
- Fixtures: add both required fields to `EvolutionTargetFixture`, fill the `evolutionTargets` entry in `fixtures/m2-synthetic/corpus.json`, and write both columns during seed.
- Prototype: add both required fields and validation messages to the create and edit dialogs in `plans/14-15-ui-prototype/harness-evolution.html`, keeping the 720px two-column form layout.
- Documentation: update 05 §4.11, 06 §5.1, 08 §9.5, and 02 F19; add `plans/fullstack-design/14-target-project-ids.md`; add an Agent Note recording the field semantics and the boundary that the values live only on the target and are not snapshotted into runs.
- Tests: API create, update, list, required, format, and historical-row cases; repository and migration; Web form required, population, emit, and error cases; E2E create and edit.

## Implementation steps

1. Add failing tests first: creating a target without either field returns 422 `PROJECT_ID_INVALID`; whitespace-only, overlong, control-bearing, and internal-whitespace input returns a field-level error; create and update then GET returns both fields; a migrated historical row reads as an empty string.
2. Add the migration and ORM columns, update the record and repository, and run the database tests.
3. Extend the service model and normalization, add the error code and details, and run the focused API tests.
4. Run `pnpm contract:generate` and update the contract snapshot.
5. Change the frontend form, reset, validation, emit, and Index mapping, and add Web unit tests.
6. Update fixtures and seed, and run the fixtures gate.
7. Update the prototype, 05/06/08/02 and chapter 14, and the Agent Note.
8. Run focused tests, types, lint, E2E, flow, and documentation gates.

## Dependencies and boundary

- Dependencies: m5-02 (target CRUD API) and m5-03 (target configuration UI).
- Delivery boundary: change only the target configuration table, API, contract, form, fixtures, prototype, and tests; do not change run creation, `evolution_runs`, the evaluation gateway, `/catalogs/targets`, or the launch wizard.
- Compatibility: both columns are additive; historical rows read as an empty string and writes require values; old clients that omit the fields receive 422.
- Non-goals: see the end of this document.

## Verification

```sh
pnpm test:api -- tests/m5-02-target-config-api
pnpm test:db
pnpm --filter @harness/web exec vitest run src/pages/evolution/targets
pnpm test:e2e -- "m5 target configuration"
pnpm typecheck:api
pnpm typecheck:web
pnpm lint:api
pnpm lint:web
pnpm contract:check
pnpm verify:flow
pnpm verify:docs
```

- Creating a target without either project ID returns 422, `details.field` names the missing field, and no row is written.
- Creating a target with both valid fields returns 201, GET returns the same values, and both columns are queryable.
- Updating only one project ID returns the new value and leaves the other unchanged.
- A historical row returns empty strings after migration; submitting an empty value returns 422, and saving after filling both succeeds.
- The frontend blocks submit while either input is empty; a filled form emits a body with both fields; edit mode populates both.
- All type, lint, E2E, contract, flow, and documentation gates pass.

## Acceptance

- The create dialog shows two required inputs, “validation-set test project ID” and “test-set test project ID”, for both skill and agent.
- Submitting with either input empty or whitespace-only is blocked and the field shows “required”; overlong input or input containing whitespace or control characters shows the format requirement under the field.
- The edit dialog populates both saved values; after a change and save, the list endpoint returns the new values.
- The `evolution_targets` table has both columns after SQLite and MySQL migrations, and historical rows hold an empty string.
- `POST` and `PUT` without the fields return 422 `PROJECT_ID_INVALID`, with `details.field` set to `validationProjectId` or `testProjectId`.
- `GET /api/evolution/targets` returns `validationProjectId` and `testProjectId`.
- Existing target CRUD, repository/subdirectory/baseline validation, the enabled switch, and delete protection behave as before.
- The prototype and the implemented form agree on field order, labels, required markers, and error placement.
- Related unit tests, E2E, types, lint, contract, flow, and documentation gates are green.

## Gates and CI

- `pnpm test:api`, `pnpm test:web`, `pnpm test:db`, `pnpm test:e2e`
- `pnpm typecheck:api`, `pnpm typecheck:web`, `pnpm lint:api`, `pnpm lint:web`
- `pnpm contract:check`, `pnpm verify:flow`, `pnpm verify:docs`
- All CI lanes pass and coverage stays at or above 80%.

## Non-goals

- Do not call an external test project API or verify that a project ID exists in this slice.
- Do not change `evolution_runs`, run creation or snapshots, the evaluation gateway, or `EvalRequest`.
- Do not add either field to `GET /api/catalogs/targets`, the launch wizard, or the run detail page.
- Do not add columns to the target configuration list table; change only the create and edit dialogs.
- Do not migrate or guess real project IDs for historical objects; historical values stay empty until an administrator fills them.
- Do not change the existing validation or error codes for `repoUrl`, `subDir`, or `defaultRef`.
