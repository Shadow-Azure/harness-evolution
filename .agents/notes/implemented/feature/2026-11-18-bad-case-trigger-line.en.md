# Agent Note: A locatable bad-case trigger line in the overview

Status: implemented

English | [中文](2026-11-18-bad-case-trigger-line.md)

## Problem

The overview's "trigger point" column has been showing `triggerAt`, which temporarily equals `createdAt` until the m9-04 coordinates land. The date and time neither locate a line in the execution flow nor read as a trigger coordinate; users can easily mistake it for the object's real trigger time. The prototype shows 0-based log lines such as `L0` and `L58` in that column, while the error-detail flow locates the same line through `SessionTree.badCases[].anchor`. What is missing is a nullable trigger-line channel from the report through the overview read model to the table cell, without breaking clients that still read `triggerAt`.

## Decision

- Add nullable `bad_cases.trigger_line` (`INTEGER`). Migration `0022` only adds the column when it is absent; historical rows stay `NULL` rather than receiving guessed values. The external contract declares the column, `BadCaseIngest` accepts an optional non-negative `triggerLine`, and catalog sync passes the same upstream field through.
- Add a required-but-nullable `triggerLine` to `BadCaseListItem`. The overview repository projects `bad_cases.trigger_line` directly in the paged query and the service maps it without extra Session reads or any derivation from `createdAt`, `metaData.line`, or event indices.
- Restore the table header to "触发点": render `L<n>` when a line exists and "—" when it does not, with both `title` and `aria-label` explaining the value or its absence. The deep link stays unchanged.
- Keep `triggerAt` in the contract for old clients, but stop using it as the overview trigger-point value. `triggerLine` and the error-detail BC marker refer to the same log-line coordinate; writers are responsible for making both agree for one case. Historical NULL rows show "—" in the overview while detail can still fall back to `anchor`.
- Cover the API value/NULL paths, the OpenAPI contract snapshot, the frontend `L<n>`/dash and accessible text, and one real normalized-Session E2E where both the overview row and the selected error-detail BC marker render the same `L2`.

## Alternatives considered

- **Keep using `createdAt` or `triggerAt` as the trigger point**: that is the defect itself. A date cannot locate a log line and misleads users into treating report time as trigger time; rejected.
- **Backfill `trigger_line` from `metaData.line`**: `metaData` is arbitrary report telemetry and its `line` may point at a source file rather than a Session log line. Store only an explicit `triggerLine`, avoiding precise-looking wrong values.
- **Use the event index as the line**: `eventIndex` is an agent-local event ordinal, not a log line; the two units differ and would place the marker on the wrong row.
- **Resolve the anchor per overview row at read time**: it would reuse detail logic but load Session events for every row on every page, degrading the list into a batch N+1. The trigger line is a stable coordinate known at report time, so one `bad_cases` column is enough.
- **Copy the detail DTO's `anchor` into the overview row**: that duplicates one coordinate in two fields, while the overview only needs the line. Keep `triggerLine` as the single field and leave detail on the existing `anchor`.
- **Batch-backfill historical NULL rows with the nearest event line**: without evidence that is fabricated location. Keep NULL and render "—"; backfill belongs to a later data path that has the original facts.

## Consequences

- Production must run migration `0022`; both SQLite and MySQL use a batch add-column, and the migration is idempotent when the column already exists.
- After the upgrade, historical bad cases have a NULL `trigger_line` and the overview shows "—" instead of a date. That is an honest empty value, not data loss. Reporters or a later data path must supply the line when it becomes available.
- `triggerLine` and the detail `anchor` agree only when the writer supplies the correct line. The read layer neither corrects nor guesses. If a report's `triggerLine` disagrees with the Session event, the overview shows the reported value while detail still uses the anchor; tests cover consistent data only.
- `triggerAt` remains in JSON and still equals `createdAt`, so old clients are unaffected. New clients must not render it as the trigger point or use it as a sort key.
- Catalog sync now accepts an upstream `trigger_line`, but stays NULL when the upstream contract does not provide it, without affecting existing syncs.
