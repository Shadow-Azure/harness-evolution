# Agent Note: Bind evolution targets to validation and test project IDs

Status: implemented

## Problem

Evolution target configuration describes where the object lives and which baseline to use, but it has no field for “which test project holds the validation set and which holds the test set”. The external test platform hosts those sets in two separate projects; if the mapping only lives in the UI or in documents, the configuration page is not the source of truth, and the information disappears after a refresh, a handover, or an environment rebuild. A later evaluation integration that receives a target also has no persisted source to distinguish the validation set from the test set.

## Decision

- Add `validation_project_id` and `test_project_id` to `evolution_targets` as `VARCHAR(128) NOT NULL DEFAULT ''`; create and update require a non-empty value after trimming, without whitespace or control characters, and return `422 PROJECT_ID_INVALID` with `details.field` and `details.reason` on failure.
- Add the same two columns to `evolution_runs`, snapshotted from the target when a run is created; historical runs read an empty string. This slice does not change the run API, run detail page, or evaluation gateway.
- Historical targets keep empty strings, remain readable, and must be filled before an edit can be saved; new targets must carry both IDs.
- The configuration table gains one merged “test projects” column with a validation-set row and a test-set row; do not split it into two table columns.
- Project IDs are opaque strings: this service does not call the external platform, does not verify existence, and does not add a uniqueness constraint.

## Alternatives considered

- **Store only in `evolution_runs.eval_config`**: the values would be entered at run creation, the target page would have no source of truth, and administrators could not bind them in advance; rejected.
- **Allow NULL in the database and make the API optional**: historical rows and old clients would be more permissive, but edits could bypass the required fields, which conflicts with the requirement; rejected.
- **Call the external test platform on save to verify the project exists**: there is no stable contract, credential model, or error semantics yet, and a network failure would become a save failure; this slice introduces no outbound call; rejected.
- **Create a separate target-to-test-project association table**: the relation is currently one-to-one and limited to two fixed kinds, so a separate table only adds joins and migration cost; rejected.

## Consequences

- Migration `0013` adds four columns; rolling back loses the IDs already entered, so export them before a rollback.
- Old clients that omit both fields receive 422; this is a deliberate required-field tightening.
- Historical targets cannot save an edit until both values are filled; historical runs keep empty snapshots.
- A later evaluation slice must read the two `evolution_runs` columns and map them into its external request; this slice only guarantees that the snapshot exists and is stable.
- Neither field is indexed or unique; object lookup still uses `(object_type, object_name)`.
