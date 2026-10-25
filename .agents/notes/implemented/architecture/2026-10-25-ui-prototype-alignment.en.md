# Agent Note: Frontend Shell Aligned With the Interaction Prototype

Status: implemented

English | [中文](2026-10-25-ui-prototype-alignment.md)

## Problem

The shared Vue shell used a dark developer-tool visual language, the `Harness Lens` brand, pill navigation, and a development-only API status pill. That conflicted with the confirmed prototype baseline and D16's light-only decision; adding more pages on the wrong foundation would increase rework and visual drift.

## Decision

- `plans/14-15-ui-prototype/harness-evolution.html` is the visual acceptance baseline. Its raw light and business-state tokens are the only color source.
- The shared shell uses a `#f4f5f7` page, `#fafbfc` header, white cards, the `Harness Evolution` brand, a 56px header, and underline navigation for Sessions, Errors, and Evolution; session surfaces use blue and Evolution uses purple.
- Login, forced password change, Loading/Empty/Error/NotFound, and the current placeholders reuse the same light tokens, font stack, and compact hierarchy. Domain pages remain owned by later milestones and the shared shell never fabricates rows.
- The real-Chrome E2E reads computed styles for page, header, card, and active-underline colors and also verifies the 390px layout without horizontal overflow.
- When compact layouts hide the brand copy, the link keeps the accessible name `Harness Evolution`; the demo-environment badge remains readable text instead of degrading to an unlabeled color dot.

## Alternatives considered

- Keep the dark developer-tool style: the prototype and D16 explicitly choose light, so later pages would all drift from acceptance; rejected.
- Replace colors only and keep the brand/navigation geometry: that would leave pill navigation, the wrong brand hierarchy, and a 68px header; rejected.
- Correct each business page later: login and shared states already inherit the wrong baseline, and this would duplicate visual work; rejected.

## Consequences

- Later pages must reuse raw tokens or semantic aliases from `tokens.css`; components must not hard-code colors.
- Element Plus remains limited to form and message controls; navigation, cards, state surfaces, and page layouts stay application-owned.
- V1 has no dark-mode toggle. The token layers leave room for a future theme, but adding one requires a separate decision.
- Shared-shell or auth visual changes require real-browser computed-style and 390px evidence.
- Responsive visual compression must not remove state semantics; color, text, and accessible names must remain recognizable together.
