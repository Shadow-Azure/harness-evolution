# Agent Note: Session problem cards lead with the description

Status: implemented

English | [中文](2026-11-18-problem-card-description.md)

## Problem

The "问题" list on the Session error page used to render the attribution summary as each card's second line: `badCaseSummary` returned a fixed "尚未完成归因分析" for unanalyzed cases and the attribution `summary` / `reason` for analyzed ones. Unanalyzed cases therefore showed no symptom at all on the session page, and the only way to read the description was to open the error detail page. The V2 prototype `FindingList` shows the problem description there, together with type/object badges, the full case ID, facts, "关联：…", and "定位 ↗". [Issue #370](https://github.com/Shadow-Azure/harness-evolution/issues/370) records this hierarchy drift and asks for a decision between keeping the attribution summary and following the prototype.

The card also truncated `badCaseId` to eight characters and never surfaced `bad_case_type`, `object_name`, or the association row, so unanalyzed cards carried neither the symptom nor the object context.

## Decision

The prototype defines the card hierarchy: the second line shows `problem.reason` (the description) rendered safely through `renderMarkdown(..., { images: false })`; the header renders `title`, the `badCaseType` (`self` / `discovery`) badge, the `objectName` badge, the full `badCaseId` deep link, and a lightweight attribution state chip; split key/value fact chips (matching the prototype and the error detail page) and "关联：`objectType` · `objectName`" follow the body, with "定位 ↗" closing the row. `badCaseSummary` is removed with it, so the attribution summary no longer appears in the list. The non-compact `BadCaseList` template adopts the compact template's overlay-button pattern: the body keeps `pointer-events: none`, links rise above the button, the whole card stays a locate button, and Markdown links in the description are not swallowed by the selection action. The V2 prototype `FindingList` now renders `renderMarkdown(f.detail)`, so prototype and implementation share one Markdown contract.

Type badges keep the error detail page's token mapping (`self` purple, `discovery` blue) instead of following the prototype stylesheet's opposite mapping: showing one case in different colors on two pages is harder to read, and the prototype's internal inconsistency is left for a separate pass.

## Alternatives considered

Keeping the attribution summary and updating the prototype and design docs was rejected: the prototype leads with the description in both `FindingList` and `FindingDescription`, and #370 exists precisely because unanalyzed cases should read the symptom on the session page; keeping the summary would still force users into the detail page. Keeping the eight-character ID was rejected: the full ID is the copy-and-investigate entry point, eight characters of a real UUID are not distinguishable, and the prototype's `fi-id` is the full ID. Putting the Markdown description inside the existing button was rejected: `renderMarkdown` emits `<a>`, an `<a>` inside a `<button>` is invalid, and clicking a link would also trigger selection; the overlay button lifts links above the button and keeps the whole card clickable. Clamping the description to a few lines was rejected: truncation is unreliable for F2P/P2P lists, hides the exact case names users need, and the prototype shows the full description. Rendering the description as plain text was rejected: #363 already defines the same field as Markdown, and the list would otherwise show raw `**` and backticks while the detail page renders formatted text.

## Consequences

Long descriptions make cards taller, so the session problem list is no longer uniform; that is the direct cost of showing the whole problem, and the prototype behaves the same. The description is covered by the card button together with the rest of the card, so its text cannot be selected, matching the compact card and the prototype; long lists can still be copied from the error detail page. Removing `badCaseSummary` leaves no attribution-summary entry in the list; attribution conclusions only appear on the error detail page and its problem card. After the prototype `FindingList` renders Markdown, prototype and production share one description typography, so future prototype screenshots can serve as the acceptance baseline. Type badge colors stay consistent between the list and the error detail page but remain opposite to the prototype stylesheet, a known unclosed difference.
