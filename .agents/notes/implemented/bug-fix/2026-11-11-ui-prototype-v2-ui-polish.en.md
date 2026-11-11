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

The eighth turn found defects in the potential bad-case list: the trigger-point column duplicates the Session detail and execution flow while consuming width; cases with an attribution report give no hint of its subject; clicking a report ID lands on the login page; the deep link selects only the case, so a case with several object attributions may open the wrong one; and the list's report IDs are synthesized per run, so they often open "no attribution yet".

The ninth turn found the bad-case list's ID only as subtext under the title: it cannot be clicked on its own, and a single case cannot be linked to directly; after adding a column, the title cell would also repeat the ID.

The tenth turn found the "source bad case" table in the evolution run detail passing `attr` explicitly, so clicking a bad-case ID landed on the attribution tab — the opposite of the "ID shows the problem, report ID shows the attribution" rule; the report-ID deep link also lacked the object, so it selected the first attribution.

The eleventh turn found the workspace switcher hugging the brand and competing with the navigation for width, while the right side of the top bar (between sync status and the user menu) sat empty; the current workspace is page-level context and reads better next to the user.

The twelfth turn found the evolution-target side card ordered by insertion, so readers cannot tell which target to tackle first; the card only exposes "associated Sessions / potential bad cases", missing the "evolvable" definition (is-target issues plus unanalyzed).

## Decision

Fix the same `plans/ui-prototype-v2/harness-evolution.html` with the smallest diff: make top-level entries non-shrinking and single-line, hiding subtitles below 1400px; disable wheel zoom and allow page scrolling on both React Flow instances, raising `minZoom` to 0.5; change `--text-faint` to `#66707c` and enlarge ticks and totals; set the Session shell to `calc(100vh - 56px)`, let the detail header's first column shrink, and ellipsize long IDs; widen the source-total column to 120px; and make the evolution-target side card a column flex container with a bottom-pinned pager. Before/after evidence lives under `plans/ui-prototype-v2/_ui-review/`.

The second turn fixes interaction state: page and workspace are written to the URL; menus close on outside click, Escape, or page change; the family-tree canvas adapts to short viewports and the legend moves into normal flow; the error-detail execution flow compresses on short viewports so the case detail is visible; switching workspace closes the old workspace's error detail and refreshes the new workspace Sessions; and the timeline only renders for the Session with real data, showing a correctly titled empty state otherwise.

The third turn makes rejected candidates score below current, uses the real iteration count in the final-evaluation subtitle, and adds a `lowerBetter` direction to `evDelta`; it defaults the add-member role to Member, lowers the admin content minimum height to 340px, labels the run-card percentage as total progress, and keeps Session stat labels on one line with tighter cell padding.

The fourth turn unifies the default policy as "the object's own self report or a trigger after the object trigger point" and adds a 10px persistent scrollbar to modal bodies; splits the third login bullet across two balanced lines and points the footer at `plans/ui-prototype-v2/`; uses "membership relation" consistently in the auth copy; and describes custom policy as composing checked rules.

The fifth turn adds two distribution blocks inside the trend card: associated Sessions normalized per target with the blue segment marking Sessions that contain potential bad cases, and a source distribution normalized by non-deduplicated count with the deduplicated count in parentheses keyed by bad case ID. Both reuse the existing `ov-obj-row` / `tg-source-obj` structure and normalized bars and share the target multi-select and time window. Launching becomes overlay-first: a new `evWizardHost()` picks the mount point by current page (`#modal-root` inside the evolution page, the global `#v2Modal` elsewhere); "start evolution" only opens the overlay, and step 4 writes the run hash and calls `V2.setPage('evo')` to leave the overview.

The sixth turn moves the source distribution out of the trend card into a new "single evolution target" card: the target select is required and defaults to the first enabled target, falling back to an empty state with a "configure targets" entry when the workspace has none; the version multi-select starts empty (meaning the newest five), its footer pins a 5 / 10 / 20 / all switch, and the card footer offers a "expand to 10" shortcut; the date range is independent of the overview filter. The card shows object-level stats (associated Sessions, potential bad cases, deduplicated, covered versions) plus two distributions: potential bad cases stacked per version and deduplicated counts per source.

The seventh turn only changes layout: the stats collapse into one divided strip; filters move into a tinted toolbar with the date range pushed right; the columns get a 1px divider and 22px inner padding, switching to a single column with a horizontal divider below 1100px; the left column gains an is / not / unanalyzed summary legend in its header; empty versions drop to 60% opacity and read "no potential bad case"; and the footnote moves to the card bottom across both columns. The target and version dropdowns now share one control: 28px tall, 8px radius, a drawn chevron, native select appearance disabled with a 30px arrow gutter, and a blue border plus 3px ring on hover and focus.

The eighth turn drops the trigger-point column and adds a "phenomenon / description" column after the report ID (the bad-case description, ellipsized with a title tooltip); `caseDeepLink` now always carries `u=<current user>` and accepts `obj=<target>`, and the error detail preselects the attribution matching that object name; the list's attribution status and report ID now come from the case's existing attribution records, and rows without a matching object attribution read "unanalyzed".

The ninth turn adds a leading "ID" column to the bad-case list: the ID uses the same deep link to open the Session error view on the matching case's problem-description tab; the title cell keeps only the title, and the empty-state colspan moves to 8.

The tenth turn switches that table back to the default deep link (`desc`), adds the `obj` parameter to the report-ID deep link, and gives `evCaseLink` a `stopPropagation` so clicking an ID does not also trigger the row action.

The eleventh turn moves `#wsPicker` out of the brand-and-nav area into `.tn-right`, after sync status and before the user menu; the popover anchors to the right (`right: 0`), and the summary cap grows to 240px with the name at 146px, so "Harness 核心研发 · 全局管理员" fits fully at 1440px and nothing overflows at 1280px.

The twelfth turn sorts the side card by is-target plus unanalyzed counts descending (ties by potential total, then name) and paginates the sorted list; each item gains "evolvable potential bad cases N (issues X; unanalyzed Y)" and the header states the sort rule.

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
- Keep the trigger-point column and only narrow it: it still duplicates the Session detail for little gain.
- Fix only the `u` parameter: the target would still open "no attribution yet", which is worse.
- Target `at=<report ID>`: the report ID is synthesized per run and does not match the attributions stored on the case.
- Make the title a link: the title is long, so its large hit area invites accidental full-page navigation.
- Keep the subtext ID and only make it clickable: it still wastes width and mixes the ID with the title.
- Render the ID as plain text with a copy button: it adds a step and still cannot be shared as a deep link.
- Keep the `attr` deep link and only explain it in the table header: it stays inconsistent with every other list and still misleads readers.
- Decide the tab from the clicked column position: it needs hit-testing, is fragile, and breaks with layout changes.
- Keep the switcher on the left and merely narrow it: the brand area stays crowded and still competes with the navigation.
- Put the switcher inside the navigation: it breaks the overview / Session / evolution / admin grouping.
- Move it into the user menu: switching workspace is frequent, and a second-level menu makes it harder to find.
- Sort silently without stating the rule: readers cannot tell the basis or the tie-break.
- Sort by total potential bad cases: that counts not-object findings too, which contradicts "evolvable".
- Summarize the evolvable count in the header only: each target has its own value, so the header cannot map to items.

## Consequences

The prototype drifts further from production frontend styling; future alignment work should treat this note and its screenshots as the reference. Review screenshots add repository weight but make each turn auditable. The 1400px threshold, 0.5 minimum zoom, and canvas height clamps are empirical; re-measure if real data lengthens labels or adds nodes. URLs use `replaceState`, so refresh restores the current page and workspace; browser back still leaves the prototype, and full history semantics would need `pushState` plus `popstate` replay. The scrollbar uses `::-webkit-scrollbar`, which stays visible in Chrome and Safari; Firefox falls back to its native scrollbar, so broader browser support would need `scrollbar-color`.

The fifth turn grows the trend card by roughly 200px at 1440px, with all three distribution definitions carried by subtitles; compressing the card later means rewriting those three notes together. The evolution overlay now depends on the global `#v2Modal`, so new full-screen overlays should reuse that mount point. Launch still writes the hash and then calls `v2SetPage('evo')`; introducing client-side routing should collapse that into a single navigation.

The sixth turn grows the overview by roughly 330px at 1440px, and the version commit IDs and timestamps are new mock data (18 for deep-research, 12 for code-review, 9 for Explore) that do not yet match the tag-based version list in the evolution wizard; a real version API should unify both. The per-version split is hash-sampled, so one bad case can appear under several versions and the potential count exceeds the deduplicated one; that is the intended definition, not cache reuse or duplicate reporting.

The seventh turn trims the card from roughly 430px to 376px at 1440px. The `.td-*` classes added for the stat strip and toolbar only serve this card, so reuse needs promotion into the shared style layer first; empty versions rely on opacity, which needs a different value under a dark theme or high-contrast mode.

The eighth turn aligns the list with the error detail, but the overview's analyzed / unanalyzed counts are no longer hash-sampled; they follow each case's attribution records and therefore shift with the mock distribution. With a real attribution API, the object-name matching should become a query by object version. Deep links gained an `obj` parameter; older links still work and fall back to the first attribution.

The ninth turn moves the ID into the first column, so that column is now one ID wide and the title column gains the horizontal room; the ID deep link still opens a new tab, and in-page navigation would use `v2OpenCase` instead.

After the tenth turn, bad-case IDs land on the problem description across both the evolution pages and the overview lists; a table that genuinely wants the attribution tab must pass `tab` explicitly and update its own copy, or it will contradict the global rule.

After the eleventh turn the top bar reads brand → navigation → sync status → workspace → user; on small screens the summary can still truncate the workspace name, so the role or name may need hiding; the right-anchored popover opens against the right edge, so narrow viewports must keep its width inside the viewport.

After the twelfth turn the side card order follows the selected time window, so a target can move between windows; the extra line adds about 18px per item, making the right column taller when five targets share a page.
