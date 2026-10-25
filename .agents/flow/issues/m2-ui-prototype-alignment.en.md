# Align frontend shell and design tokens with the interaction prototype

English | [中文](m2-ui-prototype-alignment.md)

```yaml flow
kind: issue
id: m2-09
milestone: m2
depends: []
priority: P0
status: in-progress
scope:
  - apps/web/**
  - tests/**
  - scripts/**
  - plans/**
  - reports/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
  - .github/workflows/ci.yml
  - package.json
  - pnpm-lock.yaml
adr: []
github:
  number: 92
  url: https://github.com/Shadow-Azure/harness-evolution/issues/92
```

## Background

The shared shell currently uses a near-black background, the `Harness Lens` brand, pill navigation, and a development-only health pill. This does not match the confirmed interaction prototype. The prototype and D16 require a light-first theme: a pale page surface, white cards, a 56px top bar, the `Harness Evolution` brand, underline section navigation, and blue/purple/orange/red business states. Existing login, forced-password-change, empty-state, and global-error surfaces inherit the same shell, so the visual baseline must be corrected before later domain pages amplify the drift.

## Goals

- Port the prototype's light design tokens, type stack, and monospace semantics while retaining the existing semantic-token API.
- Align TopNav, login/forced password change, shared states, and the Sessions/Errors/Evolution placeholders with the prototype's hierarchy, color, spacing, and interaction.
- Preserve existing accessibility, responsive behavior, authentication, and error recovery at 1408px and 390px, backed by real-browser prototype comparison screenshots.

## Design authority

- [Prototype acceptance baseline](../../../plans/14-15-ui-prototype/harness-evolution.html)
- [03 Frontend architecture §9 design tokens](../../../plans/fullstack-design/03-frontend-architecture.md)
- [08 Frontend implementation §1, §4, §12, §13](../../../plans/fullstack-design/08-frontend-implementation.md)
- [D16: light-only v1 with prototype token authority](../../../plans/fullstack-design/README.md)

## Implementation

- Treat the prototype's `:root` values for `--bg / --bg-panel / --bg-card / --bg-inset / --border / --text / --text-dim / --text-faint / --blue / --green / --orange / --red / --purple / --cyan / --mono` as the only color source and map them into the existing semantic tokens.
- Use a 56px light-panel top bar, a gradient square mark, the `Harness Evolution` brand, underline navigation for Sessions/Errors/Evolution, and a right-side user/demo area. Remove the non-prototype `Harness Lens`, `Vue shell`, pill navigation, and developer-facing API status pill presentation.
- Restyle login, forced password change, Loading/Empty/Error/NotFound, and the three placeholders with the prototype's white cards, pale page, 13px body type, compact spacing, and blue/purple/orange/red state language.
- Keep Element Plus limited to form and message controls; retain self-built layouts and visual components.
- Add design-token contract tests, component tests, and real Chrome visual evidence at 1408px and 390px.

## Implementation steps

1. Add failing tests for tokens, TopNav, login/password change, empty states, and narrow-viewport visual behavior.
2. Port the prototype tokens and restyle the shared shell and state components.
3. Run unit, E2E, bundle, and style gates and compare real screenshots with the prototype.
4. Run Computer Use smoke, retain before/after evidence, and confirm a clean console.

## Dependencies and boundary

- Dependencies: none
- Delivery boundary: align the current shell, auth pages, placeholders, and shared states only. Real Sessions lists, error details, execution graphs, and evolution pages remain owned by their roadmap issues.

## Verification

```sh
pnpm test:web -- app-shell auth states
pnpm test:e2e -- m1-shell
pnpm typecheck:web
pnpm lint:web
pnpm build
pnpm verify:web-style
pnpm verify:bundle
```

- Tokens match prototype colors and fonts; login, password change, three destinations, and empty states have no console errors or horizontal overflow at 1408px and 390px, and their visual hierarchy matches the prototype.

## Acceptance

- Page background is `#f4f5f7`, panel is `#fafbfc`, cards are white, body text is `#212832`, and brand/section states use the prototype's blue/purple/orange/red semantics.
- The top bar is 56px tall, brands as `Harness Evolution`, and uses underline active navigation; `Harness Lens`, `Vue shell`, and pill-style primary navigation are absent.
- Login, forced password change, Loading/Empty/Error, and the Sessions/Errors/Evolution placeholders share the light visual system without fabricated domain data.
- Real Chrome at 1408×900 and 390×844 has zero warnings/errors and no horizontal scrolling; navigation, user menu, logout, and error retry remain usable.
- Before/after screenshots and prototype key-region comparisons are reviewable, while all interaction and authentication tests remain green.

## Gates and CI

- Add design-token contracts and key visual regressions; `test:e2e` remains executable in the CI build job.
- `verify:web-style`, bundle, typecheck, lint, docs, and flow must pass.

## Non-goals

- Do not implement Sessions lists, error detail, Agent execution graphs, or evolution business pages.
- Do not introduce a dark theme toggle, change Element Plus control responsibilities, or fabricate domain data.
