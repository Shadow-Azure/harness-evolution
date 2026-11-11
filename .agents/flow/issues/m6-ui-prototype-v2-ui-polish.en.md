# V2 prototype UI readability and interaction polish

English | [中文](m6-ui-prototype-v2-ui-polish.md)

```yaml flow
kind: issue
id: m6-24
milestone: m6
depends: []
priority: P1
status: in-progress
scope:
  - plans/ui-prototype-v2/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 204
  url: https://github.com/Shadow-Azure/harness-evolution/issues/204
```

## Background

The V2 prototype carries the multi-workspace overview, Session inspection, evolution, and workspace management flows. A real-browser review found that the top navigation wraps inside words at 1408px, the family-tree wheel gesture zooms the canvas instead of scrolling the page, faint helper text lacks contrast, the Session view leaves a 44px gap at the bottom, long session IDs push detail actions to a second line, source totals overflow the chart card, and the evolution-target pager floats mid-card. These defects distort how reviewers read hierarchy and interaction intent.

## Goals

- Keep all four top-level entries on one line at desktop widths, with titles and subtitles intact.
- Let a normal wheel scroll the page; leave zoom to the bottom-right controls so the tree cannot become unreadably small by accident.
- Raise helper text and chart tick contrast, and keep key numbers inside card bounds.
- Fill the Session viewport below the top bar and keep detail actions visually grouped with the title.
- Pin the evolution-target pager to the card bottom and scroll the list in the remaining height.

## Design authority

- [03-frontend-architecture.md](../../../plans/fullstack-design/03-frontend-architecture.md): ownership of the page shell, top bar, and view switching.
- [02-features.md](../../../plans/fullstack-design/02-features.md): top-level information architecture for overview, Session errors, and evolution.
- [design-v2.md](../../../plans/ui-prototype-v2/design-v2.md): the multi-workspace and evolution-target narrative of the V2 prototype.

## Implementation

- Make top-level entries non-shrinking and single-line, tighten horizontal padding, and hide subtitles below 1340px.
- Disable wheel zoom and allow page scrolling on both React Flow instances, raise `minZoom` to 0.5, and update the legend gesture text.
- Raise `--text-faint` contrast and increase trend ticks and object totals to 10–10.5px.
- Set the Session shell height to `calc(100vh - 56px)`; allow the detail header's first column to shrink and ellipsize long session IDs.
- Widen the overview source-total column to 120px; make the evolution-target side card a column flex container with a bottom-pinned pager.
- Store before/after evidence under `plans/ui-prototype-v2/_ui-review/round1/` for turn-by-turn comparison.
- The second turn adds interaction state: page and workspace are written to the URL; workspace/user/sync menus close on outside click, Escape, and mutual exclusion; family-tree and error-flow canvases compress on short viewports with the legend moved to the top; switching workspace closes the old detail; and the timeline only renders for the Session with real data.
- Second-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round2/`.
- The third turn fixes content and state coherence: rejected iterations now score below current, removing the contradictory "rejected +2.6" state; the final-evaluation subtitle uses the real iteration count; issue-reproduction rate is colored lower-is-better; the add-member default role is Member; the admin content minimum height is tightened to 340px; the run-card percentage is labeled total progress; and Session stat labels no longer wrap.
- Third-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round3/`.
- The fourth turn unifies the default policy wording as "the object's own self report or a trigger after the object trigger point", removing mixed `+` and `∪`; keeps a persistent scrollbar in the wizard body; balances the third login bullet and corrects the baseline path; uses "membership relation" consistently in the auth copy; and describes custom policy as composing checked rules.
- Fourth-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round4/`.
- The fifth turn adds two distribution blocks inside the evolution-target overview trend card: associated Sessions normalized per target with the blue segment marking Sessions that contain potential bad cases, and a source distribution normalized by non-deduplicated count with the deduplicated count in parentheses keyed by bad case ID; both follow the target multi-select and time window.
- The fifth turn makes the overview's "start evolution" open the wizard overlay directly (new `evWizardHost()`: `#modal-root` inside the evolution page, the global `#v2Modal` elsewhere); only step 4 confirmation leaves the overview, landing on the new run detail.
- Fifth-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round5/`.
- The sixth turn moves "potential bad case source distribution" out of the trend card into a new "single evolution target" card; the trend card keeps only the associated-Session and potential-bad-case object summaries.
- The sixth turn's card has independent filters: a required target select defaulting to the first enabled target (empty state with a configure prompt when the workspace has none), a version multi-select defaulting to the newest five and expandable to 10 / 20 / all, and a date range independent of the overview.
- The sixth turn's card shows object-level stats (associated Sessions, potential bad cases, deduplicated, covered versions) plus a per-version stacked potential-bad-case distribution and a per-source deduplicated distribution.
- Sixth-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round6/`.
- The seventh turn polishes the single-target card layout: stats collapse into one divided strip, filters move into a tinted toolbar with the date range on the right, the two columns get a divider, the left header gains an is / not / unanalyzed summary legend, empty versions are dimmed, and the footnote spans the card bottom; the target and version dropdowns share one 28px control with an 8px radius and a drawn chevron.
- Seventh-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round7/`.
- The eighth turn removes the trigger-point column from the potential bad-case list and adds a "phenomenon / description" column after the report ID.
- The eighth turn fixes the attribution report deep link: it carries the current user, opens the Session error view on the attribution tab, and preselects the attribution matching `obj`; the list's attribution status and report ID now come from the case's existing attribution records.
- Eighth-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round8/`.
- The ninth turn adds a clickable leading "ID" column to the bad-case list; clicking opens the Session error view on the matching case, the title cell drops the duplicated ID subtext, and the empty-state column count is updated.
- Ninth-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round9/`.
- The tenth turn unifies link destinations: bad-case IDs always land on the problem-description tab, report IDs land on the attribution tab with the matching object preselected; the evolution "source bad case" table returns to the default deep link, and `evCaseLink` gains `stopPropagation`.
- Tenth-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round10/`.
- The eleventh turn moves the workspace switcher from the brand area into the right-hand actions (after sync status, before the user menu), anchors the popover to the right, and widens the summary to 240px so the workspace name fits.
- Eleventh-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round11/`.
- The twelfth turn sorts the evolution-target side card by is-target plus unanalyzed counts descending (ties by potential total, then name) and shows "evolvable potential bad cases N (issues X; unanalyzed Y)" under each item, with the sort rule in the header.
- Twelfth-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round12/`.
- The thirteenth turn raises the overview, evolution, and workspace-management content caps from 1200px / 1080px to 1720px, so width follows the viewport and caps only on ultra-wide screens.
- Thirteenth-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round13/`.
- The fourteenth turn moves the three status toggles into the trend card and rebuilds them as pill chips with counts (blue border and tint when on, dimmed when off), removing the duplicated header legend.
- Fourteenth-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round14/`.

## Implementation steps

1. Serve the V2 prototype locally and capture full-page baselines for overview, evolution targets, Session, and workspace management.
2. Have the analysis subagent return prioritized UI findings with screenshot evidence.
3. Have the fix subagent apply the smallest diff to `harness-evolution.html`, checking each symptom.
4. Re-test single-line navigation, wheel behavior, bottom gap, action row, and number overflow in the browser, saving before/after screenshots.
5. Repeat analysis and fix turns until no high-confidence issues remain, then run flow and documentation gates.

## Dependencies and boundary

- Dependencies: none
- Delivery boundary: only the V2 prototype HTML and review screenshots change; production `apps/web` is out of scope.

## Verification

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory plans/ui-prototype-v2
```

- Open `http://127.0.0.1:8765/harness-evolution.html?u=admin&page=overview`, `?tab=targets`, and `?page=session`.
- Each of the four top-level entries occupies one line; a wheel inside the family tree scrolls the outer pane while the viewport transform stays unchanged; the Session bottom has no gray band; the last digit of each source total is fully visible.

```sh
pnpm verify:flow; pnpm lint:docs
```

- All green.

## Acceptance

- At 1408px all four navigation entries are single-line; below 1340px subtitles are hidden with no horizontal overflow.
- In the family tree and error-detail execution flow, a normal wheel scrolls the page while the bottom-right controls still zoom and fit.
- `--text-faint` reaches at least 4.5:1 contrast on white and page backgrounds; chart dates, ticks, and object totals are legible.
- The Session view bottom edge aligns with the viewport bottom; detail actions no longer fall to a second line.
- Overview source totals and the evolution-target card show no clipped text, and the pager sits at the card bottom.
- Refresh keeps the current page and workspace; switching workspace no longer shows the previous workspace's error detail; the timeline title matches the current Session.
- Workspace, user, and sync menus close on outside click, Escape, or page change, and only one opens at a time; on short viewports the family-tree legend and case detail are visible on first screen.
- Rejected iterations in a completed run show a negative score delta; the final-evaluation subtitle iteration count matches the cluster count; an increase in issue-reproduction rate is colored as negative.
- The add-member default role is Member; the workspace-management list no longer leaves a large blank area; Session stat labels stay on one line at 1280px; and the run-card percentage is labeled total progress.
- The default policy uses the same "or" wording everywhere; the wizard body shows a persistent scrollbar when content overflows; the login page has no orphan line and its baseline path points at `plans/ui-prototype-v2/`; auth copy does not mix `membership`; and custom-policy copy matches rule-composition semantics.
- The evolution-target overview states three object-level distributions — associated Sessions, potential bad cases, and sources — and the non-deduplicated source total matches the "potential bad cases" stat.
- Clicking "start evolution" on the overview stays on the overview and completes all four steps in the overlay; after confirmation the page lands on the new run detail with `page=evo` and `#/run/<id>` in the URL.
- The trend card no longer carries the source distribution; source composition and the multi-version view appear only in the "single evolution target" card.
- The single-target card defaults to the first enabled target, shows the newest five versions by default, expands to 10 / 20 / all, and keeps stats plus both distributions in sync when the target or date range changes.
- When the workspace has no enabled targets, the card's target select is empty and shows the configure entry.
- The single-target card is no taller than 380px at 1440px; the two columns are divided; empty versions are dimmed; below 1100px the card becomes a single column.
- The potential bad-case list no longer has a trigger-point column; rows with an attribution report show its phenomenon / description after the report ID, and rows without one show —.
- Clicking a report ID opens the Session error view on the attribution tab with the matching target preselected, and never lands on the login page.
- The bad-case list starts with an ID column that opens the Session error view on that case; the title cell no longer repeats the ID.
- A bad-case ID lands on the problem description from anywhere; a report ID lands on the attribution tab with the matching target preselected.
- The workspace switcher sits in the right-hand top-bar actions, showing the full name and role at 1440px with no horizontal overflow at 1280px.
- The evolution-target side card is ordered by evolvable potential bad cases and shows that count with its issues / unanalyzed breakdown.
- At a 1720px viewport the three pages fill the visible width (≥1650px), cap at 1720px centered on a 1920px screen, and show no horizontal overflow at 1280px.
- The status chips inside the trend card show their counts, toggle the chart's stacked series, and the card header no longer repeats the legend.

## Gates and CI

- `pnpm verify:flow`: issue triple, state machine, and scope coverage.
- `pnpm lint:docs`: bilingual Agent Note pairing and document format.
- The prototype is static HTML, so `apps/web` builds and E2E are not triggered; manual screenshots are the acceptance evidence.

## Non-goals

- Do not change production Vue routes, components, or styles.
- Do not change backend APIs, data models, or quota validation.
- Do not redesign mobile layout in this turn; mobile only needs to avoid overflow.
