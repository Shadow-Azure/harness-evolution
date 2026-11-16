# Agent Note: Session latest ten and Enter-triggered exact query

Status: implemented

English | [中文](2026-11-16-session-latest-ten-ui.md)

## Problem

After m8-02 the workspace Session page already received authoritative `total` and `pendingSessions`, but its interaction still followed V1: the first request asked for `limit=100`, and every keystroke wrote the raw input to the URL through a 300 ms debounce and refetched. V2 `q` matches only a complete root session ID, so fragments are always meaningless; live filtering also makes the number of "input → request" pairs unpredictable and cannot express "clear the right-hand selection after a miss". The page needs to request only the latest ten on first load, query only when a complete ID is submitted with Enter (or the search icon), restore the latest ten by clearing and submitting again, and surface `total` plus the pending badge.

## Decision

- The list request is fixed at `limit=10`. The URL still carries only `q`, `status`, and `sort`, never `limit`; first load, filters, and history navigation all derive the same filters from the URL.
- Typing only updates local `searchInput`; it never sends a request or writes the URL. Enter or a click on the search icon submits. Submission trims the value, and an unchanged value leaves the route untouched so it cannot duplicate a request.
- Submitting a query routes to the list path (no `sessionId`) and drops the `agent`/`evidence` deep-link parameters. A miss therefore empties the right-hand overview immediately instead of retaining the old selection; a hit is selected by the existing "auto-select the first row when none is selected" logic.
- Clearing the input and submitting an empty `q` follows the same list path and clears filters, restoring the latest ten. The "restore latest ten" action in empty states calls the same function. Status and sort changes still keep the current selection, so a filter that excludes it does not empty the right panel (unchanged behavior).
- The title shows `latest {items.length} / total {total}`; with `q` it shows `matched {total}`. When `total` is absent (older response or test stub), it falls back to the page length so it never renders `undefined`.
- When `pendingSessions > 0`, the title area appends an "N pending" button. Clicking it expands one sentence: a pending session is a reported bad case whose trace has not been normalized yet, the list shows only normalized sessions, and normalized traces become visible after refreshing the page. The badge is independent of `q`/`status` and remains visible when a search misses.
- Empty states split by cause: with `q`, "no Session matched \"q\"" plus a restore action; with only a status filter, "no session matches the current filter" plus a restore action; with no filter and `pendingSessions > 0`, an explanation that pending traces are still being completed and appear after a refresh; otherwise, a note that the workspace has no bad cases yet. The right-hand empty state repeats the same search/filter/pending/no-case reason by the same priority, and only says "No Session selected" when sessions exist but none is selected.
- The placeholder becomes "enter a root session ID and press Enter", with the hint "Enter for exact query · clear and press Enter for the latest ten". The decorative magnifier SVG becomes a clickable submit button that still looks identical to the prototype. Enter during IME composition (`isComposing`) is ignored.
- The page adds no API, cache key, or contract field; this issue only consumes the `items/total/pendingSessions` returned by m8-02.

## Alternatives considered

- **Keep the 300 ms debounce**: rejected. V2 `q` is an exact full-ID match, so typing character by character only fires requests that are guaranteed to miss; the issue also requires removing live search.
- **Fetch 100 rows and slice the first ten in the browser**: rejected. `total` and `pendingSessions` need the server's authoritative definition; browser slicing separates the counters from the rows.
- **Keep the current selection when submitting a query**: rejected. A miss would keep showing a Session that is not in the result, conflicting with the design's "clear the right side on a miss"; a hit would be overwritten by auto-selection anyway.
- **Mix pending roots into the list as disabled rows**: rejected. The API states that pending contributes only to the counter and never enters `items`; fabricated rows would contradict ordering, statistics, and the meaning of `total`.
- **Replace Enter with a button**: rejected. Both the prototype and the design make Enter the primary path; the icon button exists for click access and accessibility without changing the primary interaction.

## Consequences

- Typing sends no list request; one submission sends one list request (zero when the value is unchanged). E2E verifies this with CDP request counting.
- Only complete root session IDs are supported. Title, repository, and ID-fragment search are not exposed in V2, and empty states say so explicitly.
- `total` and `pendingSessions` must not be added together: the first counts normalized roots under the current `q`/`status`, the second is independent of query and filter. The page presents them separately instead of inventing an "all reported roots" number.
- A query hit is still subject to the current `status`/`sort`. For example, entering an already-successful session ID while `status=problem` yields an empty result; that combination is allowed by design.
- The sidebar H1 remains "Session browser". The prototype sidebar says "Session", but that text is referenced by app-level navigation and existing E2E assertions; this issue does not change it, so one local interaction change does not spread into global navigation.
- The pending explanation is inline text, not a new pending-session page; the page does not poll, so pending traces require a refresh to appear, and inspecting pending roots still needs a later API or admin capability.
- E2E uses the four ws-default sessions from `fixtures:seed` for latest ten, Enter hit/miss/restore, and creates another workspace: it first verifies that a ws-default normalized root is not projected without a local bad case, then adds a pending root to check the pending badge and reverse isolation.
