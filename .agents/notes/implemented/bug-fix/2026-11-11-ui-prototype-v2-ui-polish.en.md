# Agent Note: V2 prototype UI readability and interaction fixes

Status: implemented

English | [中文](2026-11-11-ui-prototype-v2-ui-polish.md)

## Problem

Real-browser review of the V2 prototype exposed several visible defects that distort evaluation: four top-level entries wrap inside words at 1408px; the family tree treats a normal wheel as zoom, so readers trying to scroll down shrink the graph to an unreadable scale; `--text-faint` is used for chart ticks and table metadata at roughly 2.6:1 contrast; the Session shell still subtracts 100px after the sub-tabs were hidden, leaving a 44px band at the bottom; long session IDs push the detail actions to a second line; and the source-total column plus evolution-target pager do not align with card edges.

The third turn found further state and content mismatches: rejected iterations in a completed run still showed a positive delta, the final-evaluation subtitle kept the literal "M" placeholder, and a rising issue-reproduction rate was colored as a gain; the add-member dialog granted Space Admin by default; the workspace-management list left a large blank area; and the last Session stat label wrapped at 1280px.

The fourth turn found the default policy mixing `+` and `∪`, where `+` reads as addition or stacking; the wizard step 3 body overflowing `66vh` while relying on the macOS overlay scrollbar, leaving no visible scroll affordance; the third login bullet leaving an orphan line; the auth copy mixing the English word `membership`; and the custom-policy description saying rules are stacked on the default even though checked rules compose a new policy.

The fifth turn found the login footer splitting "SSO/OIDC callback" into a single-character orphan, and the note claiming the remaining accounts demonstrate the Viewer view even though the login list deliberately excludes Wang Hao, the only Viewer; the member subtitle claiming both "all permissions" and "can only grant below admin" without saying only a global admin can appoint a Space Admin; and cluster source tables, wizard headers, and the policy switch still exposing the raw `object_name` field.

The sixth turn found the evolution-target dialog marking only the validation and test project fields as required even though save validation also requires object name, repo URL, subdirectory, and baseline; and the fourth turn had pointed the login page's "visual baseline" at the current file itself, creating a self-reference.

## Decision

Fix the same `plans/ui-prototype-v2/harness-evolution.html` with the smallest diff: make top-level entries non-shrinking and single-line, hiding subtitles below 1400px; disable wheel zoom and allow page scrolling on both React Flow instances, raising `minZoom` to 0.5; change `--text-faint` to `#66707c` and enlarge ticks and totals; set the Session shell to `calc(100vh - 56px)`, let the detail header's first column shrink, and ellipsize long IDs; widen the source-total column to 120px; and make the evolution-target side card a column flex container with a bottom-pinned pager. Before/after evidence lives under `plans/ui-prototype-v2/_ui-review/`.

The second turn fixes interaction state: page and workspace are written to the URL; menus close on outside click, Escape, or page change; the family-tree canvas adapts to short viewports and the legend moves into normal flow; the error-detail execution flow compresses on short viewports so the case detail is visible; switching workspace closes the old workspace's error detail and refreshes the new workspace Sessions; and the timeline only renders for the Session with real data, showing a correctly titled empty state otherwise.

The third turn makes rejected candidates score below current, uses the real iteration count in the final-evaluation subtitle, and adds a `lowerBetter` direction to `evDelta`; it defaults the add-member role to Member, lowers the admin content minimum height to 340px, labels the run-card percentage as total progress, and keeps Session stat labels on one line with tighter cell padding.

The fourth turn unifies the default policy as "the object's own self report or a trigger after the object trigger point" and adds a 10px persistent scrollbar to modal bodies; splits the third login bullet across two balanced lines; uses "membership relation" consistently in the auth copy; and describes custom policy as composing checked rules.

The fifth turn splits the login footer into "Cookie session / user mapping" and "SSO/OIDC callback / access notes", and points the Viewer note at the user-menu switch; rewrites the member subtitle so space admins manage members, quota, and ingest but can only grant Member or Viewer; and replaces user-facing `object_name` labels with Object and "same object only", while keeping the field name in the API contract sample.

The sixth turn marks object name, repo URL, subdirectory, and baseline branch/tag as required, and restores the login baseline path to the V1 prototype `plans/14-15-ui-prototype/harness-evolution.html`.

## Alternatives considered

- Edit production `apps/web` directly: it mixes prototype review with product implementation, and this issue only covers prototype assets.
- Hide subtitles only below 1100px: the 1408px wrap remains unsolved.
- Keep wheel zoom and move the legend into a fixed overlay: the gesture conflict remains and users still zoom by accident.
- Only darken the color: contrast improves, but 9px dates on a dense weekly axis remain hard to read.
- Keep `+`/`∪` as mathematical notation: `+` reads as addition in progress and gain contexts, while `∪` depends on font support; plain-language "or" is harder to misread.
- Rely on the system overlay scrollbar: macOS hides it by default, so readers cannot tell that a short modal has more content.
- Add Wang Hao to the login account list: the extra card pushes the login button and footer below the fold at 1408 × 611, and the user menu already switches identity, so fixing the copy is cheaper.
- Keep `object_name` as a field reference: the other headers are natural language, and mixing field names hurts table readability; the API sample still keeps the field name.
- Mark only the validation and test project fields: save validation also requires object name, repo, subdirectory, and baseline, and a mismatch makes readers retry blindly.
- Keep the self-referential baseline path: readers cannot tell which prototype version the baseline means; the V1 file is still in the repo, so restoring the old path is semantically accurate.

## Consequences

The prototype drifts further from production frontend styling; future alignment work should treat this note and its screenshots as the reference. Review screenshots add repository weight but make each turn auditable. The 1400px threshold, 0.5 minimum zoom, and canvas height clamps are empirical; re-measure if real data lengthens labels or adds nodes. URLs use `replaceState`, so refresh restores the current page and workspace; browser back still leaves the prototype, and full history semantics would need `pushState` plus `popstate` replay. The scrollbar uses `::-webkit-scrollbar`, which stays visible in Chrome and Safari; Firefox falls back to its native scrollbar, so broader browser support would need `scrollbar-color`. The Viewer note on the login page depends on the identity switch in the user menu; removing that entry later requires updating the copy. The baseline path points at V1 again, so moving that folder requires a copy update; required markers must stay in sync with the `evSaveTarget` validation list.
