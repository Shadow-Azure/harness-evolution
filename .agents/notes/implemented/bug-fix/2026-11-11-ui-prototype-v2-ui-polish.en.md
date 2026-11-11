# Agent Note: V2 prototype UI readability and interaction fixes

Status: implemented

English | [中文](2026-11-11-ui-prototype-v2-ui-polish.md)

## Problem

Real-browser review of the V2 prototype exposed several visible defects that distort evaluation: four top-level entries wrap inside words at 1408px; the family tree treats a normal wheel as zoom, so readers trying to scroll down shrink the graph to an unreadable scale; `--text-faint` is used for chart ticks and table metadata at roughly 2.6:1 contrast; the Session shell still subtracts 100px after the sub-tabs were hidden, leaving a 44px band at the bottom; long session IDs push the detail actions to a second line; and the source-total column plus evolution-target pager do not align with card edges.

The third turn found further state and content mismatches: rejected iterations in a completed run still showed a positive delta, the final-evaluation subtitle kept the literal "M" placeholder, and a rising issue-reproduction rate was colored as a gain; the add-member dialog granted Space Admin by default; the workspace-management list left a large blank area; and the last Session stat label wrapped at 1280px.

The fourth turn found the default policy mixing `+` and `∪`, where `+` reads as addition or stacking; the wizard step 3 body overflowing `66vh` while relying on the macOS overlay scrollbar, leaving no visible scroll affordance; the third login bullet leaving an orphan line and the footer pointing at the old prototype path; the auth copy mixing the English word `membership`; and the custom-policy description saying rules are stacked on the default even though checked rules compose a new policy.

The fifth turn found the evolution-target overview missing object-level associated Sessions and a source view, so readers could only infer them from the side card and the trend chart; the overview page's "start evolution" push sent readers to the evolution history page before opening the wizard, adding a pointless full-page jump and discarding the overview's current time window and target filter.

The sixth turn found that keeping the source distribution inside the multi-target trend card only yields an aggregate view: readers cannot focus on one target and read its potential bad-case distribution by version and time range, and the version dimension is entirely absent from the overview, which only ever shows the `defaultRef` build.

The seventh turn found layout defects in the new card: the four stats each occupy a box with tall rows; the filter row has no separation from the body; the two columns are not divided and their titles, legend, and footnote are scattered; and empty versions look as prominent as versions with data.

## Decision

Fix the same `plans/ui-prototype-v2/harness-evolution.html` with the smallest diff: make top-level entries non-shrinking and single-line, hiding subtitles below 1400px; disable wheel zoom and allow page scrolling on both React Flow instances, raising `minZoom` to 0.5; change `--text-faint` to `#66707c` and enlarge ticks and totals; set the Session shell to `calc(100vh - 56px)`, let the detail header's first column shrink, and ellipsize long IDs; widen the source-total column to 120px; and make the evolution-target side card a column flex container with a bottom-pinned pager. Before/after evidence lives under `plans/ui-prototype-v2/_ui-review/`.

The second turn fixes interaction state: page and workspace are written to the URL; menus close on outside click, Escape, or page change; the family-tree canvas adapts to short viewports and the legend moves into normal flow; the error-detail execution flow compresses on short viewports so the case detail is visible; switching workspace closes the old workspace's error detail and refreshes the new workspace Sessions; and the timeline only renders for the Session with real data, showing a correctly titled empty state otherwise.

The third turn makes rejected candidates score below current, uses the real iteration count in the final-evaluation subtitle, and adds a `lowerBetter` direction to `evDelta`; it defaults the add-member role to Member, lowers the admin content minimum height to 340px, labels the run-card percentage as total progress, and keeps Session stat labels on one line with tighter cell padding.

The fourth turn unifies the default policy as "the object's own self report or a trigger after the object trigger point" and adds a 10px persistent scrollbar to modal bodies; splits the third login bullet across two balanced lines and points the footer at `plans/ui-prototype-v2/`; uses "membership relation" consistently in the auth copy; and describes custom policy as composing checked rules.

The fifth turn adds two distribution blocks inside the trend card: associated Sessions normalized per target with the blue segment marking Sessions that contain potential bad cases, and a source distribution normalized by non-deduplicated count with the deduplicated count in parentheses keyed by bad case ID. Both reuse the existing `ov-obj-row` / `tg-source-obj` structure and normalized bars and share the target multi-select and time window. Launching becomes overlay-first: a new `evWizardHost()` picks the mount point by current page (`#modal-root` inside the evolution page, the global `#v2Modal` elsewhere); "start evolution" only opens the overlay, and step 4 writes the run hash and calls `V2.setPage('evo')` to leave the overview.

The sixth turn moves the source distribution out of the trend card into a new "single evolution target" card: the target select is required and defaults to the first enabled target, falling back to an empty state with a "configure targets" entry when the workspace has none; the version multi-select starts empty (meaning the newest five), its footer pins a 5 / 10 / 20 / all switch, and the card footer offers a "expand to 10" shortcut; the date range is independent of the overview filter. The card shows object-level stats (associated Sessions, potential bad cases, deduplicated, covered versions) plus two distributions: potential bad cases stacked per version and deduplicated counts per source.

The seventh turn only changes layout: the stats collapse into one divided strip; filters move into a tinted toolbar with the date range pushed right; the columns get a 1px divider and 22px inner padding, switching to a single column with a horizontal divider below 1100px; the left column gains an is / not / unanalyzed summary legend in its header; empty versions drop to 60% opacity and read "no potential bad case"; and the footnote moves to the card bottom across both columns.

## Alternatives considered

- Edit production `apps/web` directly: it mixes prototype review with product implementation, and this issue only covers prototype assets.
- Hide subtitles only below 1100px: the 1408px wrap remains unsolved.
- Keep wheel zoom and move the legend into a fixed overlay: the gesture conflict remains and users still zoom by accident.
- Only darken the color: contrast improves, but 9px dates on a dense weekly axis remain hard to read.
- Keep `+`/`∪` as mathematical notation: `+` reads as addition in progress and gain contexts, while `∪` depends on font support; plain-language "or" is harder to misread.
- Rely on the system overlay scrollbar: macOS hides it by default, so readers cannot tell that a short modal has more content.
- Keep the overlay on `#modal-root` while temporarily unhiding `view-evo`: it flashes the evolution history page and still binds the mount point to page visibility.
- Keep the "jump to the evolution page, then open the wizard" flow: the extra full-page switch discards the overview's time window and target filter.
- Show only deduplicated or only non-deduplicated source counts: the former contradicts the list row count, and the latter cannot explain how 31 potential bad cases break down.
- Keep the source distribution inside the trend card behind a target filter: the trend card is a multi-target comparison, so a single-target filter would mix two different scopes in one card.
- Split the card's potential cases by the session-to-version assignment: the current model maps one session to one version, leaving most versions with no data.
- Show every version by default: 18 versions fill two screens and contradict the "newest five by default" requirement.
- Only tighten the spacing of four stat cards: they still consume a row each, so density does not improve.
- Repeat the legend on every row: it duplicates the inline breakdown and adds noise.
- Use a single column at desktop widths too: it wastes horizontal space and prevents reading versions and sources side by side.

## Consequences

The prototype drifts further from production frontend styling; future alignment work should treat this note and its screenshots as the reference. Review screenshots add repository weight but make each turn auditable. The 1400px threshold, 0.5 minimum zoom, and canvas height clamps are empirical; re-measure if real data lengthens labels or adds nodes. URLs use `replaceState`, so refresh restores the current page and workspace; browser back still leaves the prototype, and full history semantics would need `pushState` plus `popstate` replay. The scrollbar uses `::-webkit-scrollbar`, which stays visible in Chrome and Safari; Firefox falls back to its native scrollbar, so broader browser support would need `scrollbar-color`.

The fifth turn grows the trend card by roughly 200px at 1440px, with all three distribution definitions carried by subtitles; compressing the card later means rewriting those three notes together. The evolution overlay now depends on the global `#v2Modal`, so new full-screen overlays should reuse that mount point. Launch still writes the hash and then calls `v2SetPage('evo')`; introducing client-side routing should collapse that into a single navigation.

The sixth turn grows the overview by roughly 330px at 1440px, and the version commit IDs and timestamps are new mock data (18 for deep-research, 12 for code-review, 9 for Explore) that do not yet match the tag-based version list in the evolution wizard; a real version API should unify both. The per-version split is hash-sampled, so one bad case can appear under several versions and the potential count exceeds the deduplicated one; that is the intended definition, not cache reuse or duplicate reporting.

The seventh turn trims the card from roughly 430px to 376px at 1440px. The `.td-*` classes added for the stat strip and toolbar only serve this card, so reuse needs promotion into the shared style layer first; empty versions rely on opacity, which needs a different value under a dark theme or high-contrast mode.
