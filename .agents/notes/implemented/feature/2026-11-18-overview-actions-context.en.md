# Agent Note: V2 overview workflow actions and operational context

Status: implemented

English | [中文](2026-11-18-overview-actions-context.md)

## Problem

m8-04 shipped the overview with read-only statistics, trend, source distribution, and list. It explicitly rejected the prototype's right-hand quota/ingest/workspace sidebar and the expandable source-by-time matrix: the former was judged to duplicate workspace administration, and the latter had no object-by-bucket counter behind m8-03. The m12-08 production/prototype comparison now lists both as required V2 gaps and asks for actions that reuse the existing admin page and launch wizard without a second write path.

## Decision

- The bad-case overview header renders "上报接入" and "启动自进化" only under `canManageWorkspace(currentRole)`. The first targets the current workspace's `admin?tab=ingest`; the second opens the existing `LaunchWizard`. Unauthorized roles see a read-only notice instead of a bypassable empty link. A successful launch pushes the existing run detail route, so browser back still returns to the overview URL.
- Operational context reuses two existing sources: summary `used/quota/sources` and session `memberCount/spaceAdminCount/role`. The ingest address is derived from the current workspace id as `POST /api/workspaces/:wid/bad-cases`, and the copy button copies only that address. It never reads or copies a credential and adds no member or credential request.
- Operational context and the trend card form a desktop two-column grid, with the bad-case list spanning the next row. At ≤1024px the grid becomes one column ordered trend → list → context, so auxiliary information never precedes primary content.
- The source-by-time matrix keeps the existing sources endpoint: on expand, each bucket is mapped to its inclusive window using the grain the server actually returned, that bucket's source aggregate is read, and the rows are merged by source. Bucket windows are disjoint, so the merge is exact for the active window and object filter; it never depends on the current list page or fabricates missing buckets.
- The matrix handles at most 31 time buckets. Above that it asks for a weekly/monthly grain instead of issuing hundreds of aggregate reads. Bucket reads run in bounded groups of four; a failure shows a block-level error and retry.
- The former "read-only view · filters live in the address bar" notice is replaced by the V2 actions/read-only notice. The URL remains the single source of filter state; entry navigation and return do not change the existing `tab/range/grain/objects/page/type` contract.

## Alternatives considered

- **Add an object-by-bucket field to the sources response**: rejected. m12-08's delivery boundary explicitly adds no API; the field patch belongs in a separate subtask and this issue must not grow into contract and backend work.
- **Stitch the matrix from the current eight-row page**: rejected. Cross-bucket counts would be systematically low and would change with paging; that is fabricated data, not a degradation.
- **Call trend once per source**: rejected. The trend endpoint reads every row in the window and buckets in Python, so per-source calls amount to repeated full reads. Per-bucket sources aggregates are narrower and total roughly one window scan.
- **Use the admin members/credentials endpoints for current-workspace information**: rejected. The overview only needs the member counts and role already in the session; pulling the member directory would duplicate administration and add first-paint requests.
- **Render disabled buttons for unauthorized roles**: rejected. Both the prototype and the permission matrix hide write entry points; a disabled button still implies a bypassable action.

## Consequences

- The m8-04 facts "the page has no write operation", "no SourceMatrix", and "the sidebar is rejected" are superseded by this Note. The m8-04 Note keeps its original URL and independent-block decisions and links back here.
- The matrix issues one request per time bucket (fourteen for the default 90-day weekly window). The 31-bucket ceiling means a 90-day daily window must switch grain first. That is the explicit cost of having no API field; a future object-by-bucket field can replace it with one read.
- Member/administrator counts in operational context come from the session cached at login, so membership changes appear only after a session refresh. They are never used for authorization; the `workspace` role remains authoritative.
- Read-only members still see the ingest address and source distribution, but not the header write actions or the admin request example. Ingest credentials remain readable only by authorized roles on the workspace admin page.
