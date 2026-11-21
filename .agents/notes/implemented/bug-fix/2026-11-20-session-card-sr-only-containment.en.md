# Agent Note: Session card sr-only escapes the scroll clip

Status: implemented

English | [中文](2026-11-20-session-card-sr-only-containment.md)

## Problem

The production Session error view showed a third window scrollbar ([GitHub #434](https://github.com/Shadow-Azure/harness-evolution/issues/434)). At 1500×837 `document.scrollingElement.scrollHeight = 1895` while `clientHeight = 837`; every visible container bottoms out at 837, and hiding `.session-list` drops the document back to 837 immediately.

The cause is the status text `<span class="sr-only">` in `SessionCard.vue`: it uses `position: absolute`, while neither `.session-card` nor `.session-list` has a positioned ancestor, so the element's `offsetParent` becomes `body`. Its containing block is the initial containing block, `.session-list`'s `overflow-y: auto` is not in that chain, and the clip does not apply; the box's static position in the card title row is counted in the root element's scrollable overflow. With 10 production Sessions the last card's `.sr-only` sits at y≈1830, stretching the document to 1895; the browser paints the window scrollbar and the page can scroll into the blank band below both columns.

The existing regression missed it because the m3 e2e and the synthetic fixture only have 4 Sessions; the last card's `.sr-only` is still inside 837, the document stays 837, and #422's "document does not scroll" assertion stayed green.

## Decision

Add `position: relative` to `.session-card` so `.sr-only` resolves its containing block to the card and is clipped again by `.session-list`'s `overflow-y: auto`; the visible layout and the accessible text do not change. Apply the same rule while auditing the other `.sr-only` sites: `.attribution` in `AttributionReport.vue` and `.version-label` in `VersionLabel.vue` also get `position: relative`.

The m3 e2e gets two assertions in the same 1500×837 scenario: no `.session-card .sr-only` may have `offsetParent === body`, and after cloning the list up to 10 cards, `document.scrollingElement.scrollHeight` must equal `innerHeight`. The clones only create the 10-card layout and are removed after the measurement; the shared fixture is untouched.

`plans/fullstack-design/08-frontend-implementation.md` §5.5 records the rule: an absolutely positioned assistive text (`.sr-only`) inside a scroll container must use an element in that container as its containing block.

## Alternatives considered

- **Put `overflow: hidden` on `body` or `html`**: it hides the third scrollbar but also breaks document scrolling on the overview and evolution pages, and does not fix the cause; rejected.
- **Change `.sr-only` to `position: static`**: it avoids the escape but occupies a 1px layout slot in the flex row and may change alignment, and the three components inline their own `.sr-only`; rejected in favor of keeping the standard visually-hidden recipe and adding positioned ancestors.
- **Grow the fixture to 10 Sessions**: the shared fixture's card count is asserted by several cases, and the blast radius goes beyond this layout defect; the layout regression does not depend on the data source, so the test clones real cards to reach the 10-card layout; rejected.
- **Add only a document-height assertion**: with 4 Sessions the document is already 837 and the bug is invisible; the `offsetParent` assertion is required to lock the root cause; rejected.

## Consequences

- The production document returns to 837 and only the left and right scrollbars remain; the visible card and right-column layout is unchanged.
- On the unfixed code the new assertions fail: four `.sr-only` elements have `offsetParent === body` and the 10-card layout is about 1895 tall; after the fix they report 0 and 837.
- New convention: any `.sr-only` added inside a scroll container must sit under a positioned ancestor in that container, otherwise its static position stretches the document.
- `.sr-only` can still be reused by containers without a positioned ancestor; new sites follow the rule above, and no global lint was added.
