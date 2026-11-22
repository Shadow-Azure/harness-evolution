# Agent Note: V2 page width for the target config page

Status: implemented

English | [中文](2026-11-22-target-config-page-width.md)

## Problem

The workspace shell's `.workspace-main .evolution-page-frame` caps every workspace page at a 1080px content column, but the target config page has 8 columns per [08 §9.5](../../../../plans/fullstack-design/08-frontend-implementation.md), wider than the V2 prototype's 6 columns. At the production 1408×788 viewport on 2026-11-22, the 8-column table was about 1071px wide while the table scroller inside the content column had a 996px `clientWidth`, so the rightmost 「Actions」 column was clipped by the horizontal scroller. At 1920px the content column was still 1080px, leaving 420px empty on each side. The V2 prototype's [`.evo-app .wrap`](../../../../plans/ui-prototype-v2/harness-evolution.html) is `width: min(100%, 1720px)`, giving a 1360px content panel at the same viewport. Measurements and the candidate fix are in GitHub #498.

## Decision

- Widen only the target config page to the V2 page width: add `.workspace-main .evolution-page-frame.target-config-page { width: min(1720px, 100%); }` to the shared stylesheet. The shared `.workspace-main .evolution-page-frame` stays at 1080px and continues to apply to the evolution list and workspace admin pages.
- Reuse the existing frame's 24px inline padding and `margin: 0 auto` centering; add no content wrapper, page-width class or table-column change. The 8 columns, fields, sorting and actions stay as they are.
- E2E asserts page and content widths at 1408×788, 1920×1080 and 1024×768 (1408/1360, 1720/1672, 1024/976), table `scrollWidth === clientWidth`, and the actions column's right edge staying inside the scroller; 1024 must keep the table's horizontal-scroll fallback. At 1408 and 1920 the page itself must have no horizontal overflow.

## Alternatives considered

- **Change the shared `.workspace-main .evolution-page-frame` to 1720px**: this would also change the evolution list and workspace admin page widths, beyond #498's page scope; whether those pages should also use the V2 width needs a separate issue and product confirmation. Rejected.
- **Compress the repository column or hide the table's horizontal scrollbar**: this does not give the constrained page width back to the table, the actions column can still be clipped, and information readability suffers. Rejected.
- **Add a wrapper or a second page-width class to the target config page**: the existing frame already provides padding and centering, so a single-page selector is enough; a new structure would only widen the change surface. Rejected.
- **Change the table `min-width` so 8 columns squeeze into 996px**: this avoids overflow only by compressing columns, contradicts the prototype and design document's column structure, and hurts long repository URLs and project IDs. Rejected.

## Consequences

- At 1408×788 the content panel is 1360px, all 8 columns and 「Edit / Disable / Delete」 are fully visible, and the table has no horizontal scrollbar; at 1920×1080 the content column caps and centers at 1720px; at 1024×768 and below the table keeps horizontal scrolling and the page itself does not overflow horizontally.
- The evolution list and workspace admin pages stay at 1080px; unifying them at 1720px needs a separate issue.
- The single-page rule depends on the page root class `.target-config-page`; if that class changes, the `main.css` selector and the E2E assertions must follow.
- The real-browser regression lives in `m5-target-config` and keeps using the synthetic fixture; it never reads production configurations or Session content.
