# Agent Note: Type and title normalization for upstream catalog sync

Status: implemented

English | [中文](2026-11-25-bad-case-sync-type-title-normalization.md)

## Problem

The catalog sync feeds each upstream bad_cases page into strict `BadCasePage` validation, and `BadCaseItem` treated upstream data as already satisfying the local `bad_cases` constraints: `bad_case_type` had to be a non-empty string of 1–16 characters and `title` was capped at 255. Real upstream data already contains items with a null `bad_case_type` and overlong titles, and page validation is all-or-nothing — one such item fails the whole page's `model_validate`, which surfaces as `BAD_CASE_QUERY_INVALID_RESPONSE`; the page rolls back, the cursor does not move, and the next scheduled tick retries the same page from the same cursor, so one dirty row becomes a poison pill that blocks every later bad case. m6-17 already degraded empty `object_name` / `object_type` values ([2026-10-30-bad-case-catalog-sync.en.md](../feature/2026-10-30-bad-case-catalog-sync.en.md)) but explicitly listed these two fields as non-goals, and a 200-character rule did not exist anywhere in the code; the measured cutoff was the 255-column width.

## Decision

Keep m6-17's "relax the transport, normalize at write" layering and change only two places. Transport, `BadCaseItem`: `bad_case_type` becomes optional (None or missing is accepted, non-null values still validate against 1–16 characters) and `title` drops the 255 cap while keeping non-empty; `extra="forbid"`, the timezone validation, and `BadCasePage`'s sort, uniqueness, and limit/total checks are untouched. Write mapping, `_row`: `bad_case_type=item.bad_case_type or "self"` and `title=item.title[:200]`; whenever either rule fires, one structured info record is logged with extras carrying `badCaseId` and the hit field names, and no status column is added. Table shape and column width, read paths, page transactions, and cursor semantics stay unchanged.

## Alternatives considered

- **Default and truncate inside the transport model**: rewriting values at parse time would make the model stop mirroring the upstream shape, upstream drift would become invisible at that layer, and any future consumer would receive rewritten data; normalization is a local write policy, not part of the upstream contract. Rejected.
- **Keep the strict model and wait for upstream to fix its data**: the defect exists precisely because upstream and local contracts drifted while the sync layer had nowhere to stand; without upstream cooperation the sync stalls forever, every retry consumes budget, and the popover shows only a stable error code with no pointer to the case or field. Rejected.
- **Skip bad rows and commit the rest**: that breaks page atomicity and cursor semantics and creates silent data holes; the issue lists it as a non-goal. Rejected.
- **Truncate titles at 255 (following the column width)**: titles of 205–255 characters would land verbatim, contradicting the required 200-character rule; 200 is the established short-title budget on the attribution side (`attribution.py` and `attribution_executor.py` both take `[:200]`), and read paths consume 200. Rejected.
- **Tighten the `title` column to 200 with a migration**: after truncation the write cap is 200 and can never reach the 255 column width; changing the width would drag in existing rows and a migration, and this issue changes no tables. Rejected.

## Consequences

- Pages with null/missing types or overlong titles parse and land again, and the sync keeps advancing; explicit `self` / `discovery` values and titles up to 200 characters stay verbatim.
- Title truncation is lossy: anything beyond 200 characters is dropped forever, and since the cursor only moves forward old ids are never re-pulled, so truncated content cannot be recovered; acceptable because `title` is by design a short headline that read paths and the attribution budget consume at 200.
- The column width stays 255: the 200 write cap leaves headroom, and this fix adds no migration and touches no existing rows.
- The only observability for normalization is the info log (`badCaseId` plus the hit field names), used to tell upstream drift from local logic errors; truncated values are never written back upstream.
- Illegal shapes beyond the two fields (missing required fields, an empty `title`, a type longer than 16 characters, naive timestamps, and so on) still fail the whole page with rollback, and the existing semantics of a bad page never advancing the cursor are unchanged.
