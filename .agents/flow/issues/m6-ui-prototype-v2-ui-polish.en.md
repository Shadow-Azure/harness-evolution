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
- The fourth turn unifies the default policy wording as "the object's own self report or a trigger after the object trigger point", removing mixed `+` and `∪`; keeps a persistent scrollbar in the wizard body; balances the third login bullet; uses "membership relation" consistently in the auth copy; and describes custom policy as composing checked rules.
- Fourth-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round4/`.
- The fifth turn fixes login and member copy: the login footer is split into two balanced lines, and the read-only note points to the user-menu switch; the member sentence says space admins manage members, quota, and ingest but can only grant Member or Viewer; user tables replace the raw `object_name` field with Object, and the policy switch reads "same object only".
- Fifth-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round5/`.
- The sixth turn marks every validated field in the evolution-target dialog as required: object name, repo URL, subdirectory, and baseline branch/tag are all checked on save, so their labels now match the validation list; the login page's visual baseline path returns to the V1 prototype, removing the self-reference introduced in the fourth turn.
- Sixth-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round6/`.
- The seventh turn fixes data and role labels: the `ws-harness` creation date moves from 2026-09-12 to 2026-08-01, before its earliest Session (2026-08-23); the user-menu demo identity reuses the login page's display-role calculation, so Space Admins are no longer labeled "regular user".
- Seventh-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round7/`.
- The eighth turn puts three destructive actions behind an explicit confirmation: removing a member, regenerating the ingest credential, and removing an evolution target each explain the consequence first, leave state untouched on cancel, and act only after confirmation; the dialog shares one `v2Confirm` helper and document-level click dispatch.
- Eighth-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round8/`.
- The ninth turn completes keyboard behavior: the confirm dialog focuses Cancel on open, Escape closes it and skips the pending action, and ordinary form dialogs also close on Escape; the confirm dialog gains `role="dialog"`, `aria-modal`, and a title association.
- Ninth-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round9/`.
- The tenth turn restores focus after a dialog closes: the trigger is recorded on open and refocused on close when it is still in the document, falling back naturally when the action removed the trigger instead of dropping keyboard users on the page root.
- Tenth-turn evidence lives under `plans/ui-prototype-v2/_ui-review/round10/`.

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
- The default policy uses the same "or" wording everywhere; the wizard body shows a persistent scrollbar when content overflows; the login page has no orphan line and its baseline path points at `plans/14-15-ui-prototype/`; auth copy does not mix `membership`; and custom-policy copy matches rule-composition semantics.
- The login footer has no single-character orphan and the read-only note matches the available user-menu switch; member permissions are not self-contradictory; and user tables no longer expose `object_name`.
- Required markers in the evolution-target dialog match save validation; the login page's visual baseline points at the V1 prototype rather than the current file.
- A workspace's creation date precedes its earliest Session; the user menu, login page, and header show the same role label for the same user.
- Removing a member, regenerating the ingest credential, and removing an evolution target all ask for confirmation first; cancelling leaves the member list, credential, and target totals unchanged, while confirming applies the change and shows a toast.
- The confirm dialog focuses Cancel on open, Enter cancels, and Escape closes it; closing skips the pending action, and ordinary form dialogs also close on Escape and return focus to the trigger.
- After cancelling or pressing Escape, focus returns to the button that opened the dialog; confirming an action that removed that button raises no error.

## Gates and CI

- `pnpm verify:flow`: issue triple, state machine, and scope coverage.
- `pnpm lint:docs`: bilingual Agent Note pairing and document format.
- The prototype is static HTML, so `apps/web` builds and E2E are not triggered; manual screenshots are the acceptance evidence.

## Non-goals

- Do not change production Vue routes, components, or styles.
- Do not change backend APIs, data models, or quota validation.
- Do not redesign mobile layout in this turn; mobile only needs to avoid overflow.
