# Agent Note: Keep disabled evolution targets visible in the overview side list

Status: implemented

English | [中文](2026-11-26-disabled-target-overview-sidebar.md)

## Problem

The production "Overview → Evolution targets" page reads only `enabled=true` configuration: `TargetOverviewService._analyses()` always passes `enabled_only=True`, and the `summary/items/total` of `GET /overview/targets` also cover enabled targets only. Once an administrator disables a target, its configuration disappears from the whole overview; the page neither shows that it still exists nor offers a way to re-enable it. The user confirmed that disabled targets should stay in the side list while continuing to stay out of every other statistic (GitHub #626).

## Decision

- Contract additive: `TargetOverviewListResponse` gains `disabled: [TargetOverviewDisabledItem]` carrying only `targetId/objectType/objectName/attributionSkillName/defaultRef`; `TargetOverviewItem` and `TargetOverviewSummary` keep their fields, and generated types come from `pnpm contract:generate`.
- The server's `list_targets()` performs one extra same-workspace read with `enabled_only=False`, filters `enabled=false`, and writes them into `disabled` ordered stably by object name, type then id; that list is page-independent and returns the workspace's full set on every page. `trend`, `cases`, `detail`, `summary`, `items` and `total` still use enabled targets only.
- The web data flow keeps `disabled` and `items` on separate channels: `TargetsOverview` passes `disabled` straight to `TargetSideList` and never merges it into `targetItems`, so filters, trend, distributions, the detail selector and the potential bad-case list cannot see disabled targets by construction.
- `TargetSideList` joins enabled and disabled rows into one paginated sequence (five per page): after the enabled rows it appends the dashed group "已停用对象 · 仅展示，不参与统计"; disabled rows are greyed out, carry the "已停用" badge, show the attribution Skill, and offer enable/edit/remove. They have no selection button and never enter `selected`.
- Enabling reuses the existing `useEvolutionTargets().updateTarget`: it assembles an `EvolutionTargetWrite` from the current configuration (`enabled=true`, preserving `attributionPackageId`) and goes through the normal server-side repository/ref validation. Success invalidates the overview and returns to page one; failure shows the server error with no local optimistic switch.
- Tests cover the API `disabled` list and the `summary/total` scope, the component's group order/badge/no-selection/enable-edit-remove events, and E2E visibility of the disabled row, its absence from selectors, and statistics recovering after enabling.

## Alternatives considered

- **Merge disabled targets into `items` and add an `enabled` field**: rejected. `items` is the single source for `evolvable` ordering and all statistics; merging forces filters, charts, detail selectors and the potential bad-case list to each exclude disabled rows, and any missed spot puts them back into statistics.
- **Add a `GET /overview/targets/disabled` endpoint**: rejected. Disabled metadata shares one page, permission and refresh cadence with the target list; a separate endpoint only adds one more request and a cache key, and the issue explicitly rules out new endpoints.
- **Join disabled rows into `targetItems` on the client and filter afterwards**: rejected. That turns "disabled targets stay out of statistics" from a server contract into an accident of frontend code, with no protection beyond component tests.
- **PATCH only the `enabled` field when enabling**: rejected. The current API only offers a whole-object `PUT`; adding partial update expands the contract and validation surface, while assembling the full existing configuration reuses current validation and error mapping.
- **Optimistically move the row into the enabled list**: rejected. Enabling validates repository/ref on the server and can fail; an optimistic switch would show wrong statistics on failure, while the issue requires showing only the server error.

## Consequences

- The overview side list gains a "disabled targets" group; the six header counters, trend, both distributions, the per-target analysis card, filter dropdowns and the potential bad-case list keep their values and options.
- The side-list pager total includes disabled targets, which the issue permits; enabled targets still sort by `evolvable` descending, five per page.
- `GET /overview/targets` performs one extra same-workspace query for disabled targets per request; it is independent of the enabled-target analysis and never triggers version resolution or matching.
- Enabling still runs the full target write validation: an unreachable repository or missing ref leaves the target disabled and shows the server error; the target-configuration page's enable switch and form fields are unchanged.
- Disabled targets only offer enable/edit/remove, with no historical statistics or detail drill-down; the existing `enabled=false` semantics for the launch wizard, bound batches, attribution and runs are unchanged.
