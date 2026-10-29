# Launch wizard config entry as an underlined hint link

English | [中文](m6-wizard-config-link.md)

```yaml flow
kind: issue
id: m6-10
milestone: m6
depends:
  - m5-05
priority: P1
status: in-progress
scope:
  - apps/web/**
  - tests/**
  - plans/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr:
  - ../../notes/implemented/feature/2026-10-27-target-config-ui.md
github:
  number: 150
  url: https://github.com/Shadow-Azure/harness-evolution/issues/150
```

## Background

### What is wrong

In step 1 of the "launch evolution" wizard, the entry to the evolution target configuration is a standalone `⚙` gear button to the right of the target selector: a bare 13px gray glyph with no border or background that visually blends into the form; the hint text even instructs users to "click the gear to open the configuration page", placing the discovery cost on an almost invisible glyph.

### Symptoms

- In the target row, the gear button sits right next to the target select, and users hardly notice it is a clickable entry.
- The hint "Unconfigured targets do not appear in the list; click the gear to open the configuration page." directs users to hunt for a barely visible character.
- User feedback: remove the gear button, merge the action into the hint text, and underline the clickable "configuration page" words.

### Impact

- Users without a configured target cannot find the entry, the wizard stalls on an empty list, and the task is interrupted.
- Discoverability and affordance fall short of the basic expectation that a clickable thing looks clickable.

### Root cause

- The gear button in `LaunchWizard.vue` carries its affordance solely through a 13px `color: var(--text-faint)` glyph with no boundary or hover area hint.
- The hint text mixes the action target (the gear) into prose instead of turning the clickable target itself into a link.
- The prototype `harness-evolution.html` never had a gear entry in wizard step 1; the app diverged when it added one.

### Suggestion

- Remove the gear button and its styles so step 1 keeps only form controls.
- Change the hint to "Unconfigured targets do not appear in the list; click the configuration page to continue." where "configuration page" is a blue solid-underlined inline button: keyboard focusable, visible focus, clear hover feedback, reusing the existing "close the wizard → open `/evolution/targets`" behavior.
- Sync the prototype and design docs so the prototype stays the visual authority for this entry.

## Goals

- Wizard step 1 no longer renders a gear button; the "configuration page" link inside the hint is discoverable, clickable, and keyboard operable.
- Clicking behaves like the old entry: close the wizard and land on `/evolution/targets`; candidate targets and versions refresh as before (existing `["catalogs"]` / `["evolution","targets"]` invalidation chain).
- Prototype, design docs, tests, and implementation stay consistent with an automated regression path in place.

## Design authority

- [plans/fullstack-design/08-frontend-implementation.md §9.2](../../../plans/fullstack-design/08-frontend-implementation.md): wizard step 1 form and config entry semantics.
- [plans/fullstack-design/08-frontend-implementation.md §16](../../../plans/fullstack-design/08-frontend-implementation.md): only configured and enabled targets can launch; the entry lives in wizard step 1.
- [plans/fullstack-design/02-features.md F19](../../../plans/fullstack-design/02-features.md): evolution target configuration feature and entry description.
- [plans/fullstack-design/09-review-guide.md](../../../plans/fullstack-design/09-review-guide.md): wizard step 1 → configuration page review mapping.
- [plans/fullstack-design/README.md D13](../../../plans/fullstack-design/README.md): evolution target configuration decision entry.
- On conflicts, the linked sections and the `plans/14-15-ui-prototype/harness-evolution.html` prototype win.

## Implementation

- Remove the gear button next to the target select and the `.gear` styles in `LaunchWizard.vue`.
- Turn the hint into the inline-link version; "configuration page" becomes `button.cfg-link` (solid underline, `--blue`, darker and thicker on hover, visible `:focus-visible`), reusing `goTargetConfig()`.
- Unit tests assert the hint-line link, its copy, and the navigation, and assert the gear is gone.
- The "gear target config navigation" E2E scenario enters the configuration page through the wizard hint link, keeping an automated regression path.
- Sync the prototype (`.wz-note` / `.cfg-link` and the `wz-target-config` action branch), the five design-doc mentions, and the owning Agent Note.

## Implementation steps

1. Failing tests first: unit test asserts no gear, the `wizard-target-config-link` inside the hint, and that clicking emits `close` and routes to `/evolution/targets`; rewrite the E2E scenario to the wizard hint link and watch it fail.
2. Implement the button swap and `.cfg-link` styles in `LaunchWizard.vue`, matching the prototype's visual convention.
3. Bring the E2E scenario back to green.
4. Sync the prototype, the design docs (08/05/02/09/README), and the owning Agent Note (paired locales + `record:i18n`).
5. Run focused unit tests, web typecheck and lint, E2E, flow and docs gates, design-token and bundle gates.

## Dependencies and boundary

- Depends on: m5-05
- Boundary: only the step 1 config entry form, the hint copy, the matching tests, and prototype/doc sync; the configuration page itself and the catalog invalidation semantics do not change.

## Verification

```sh
pnpm --filter @harness/web test -- LaunchWizard
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e --pattern "target config"
pnpm verify:flow
pnpm lint:docs
pnpm verify:web-style
pnpm verify:bundle
```

- Wizard step 1 renders no gear button; the underlined "configuration page" in the hint is keyboard focusable, and clicking closes the wizard and lands on `/evolution/targets`.
- Unit tests, E2E, typecheck, lint, flow, and docs gates are all green.

## Acceptance

- The gear button (including the `.gear` styles and its accessible naming) is fully removed.
- "Configuration page" in the hint is a solid-underlined link with hover feedback, keyboard operability, visible focus, and working navigation.
- Returning from the configuration page and reopening the wizard refreshes target/version candidates as before.
- Unit tests, E2E, and docs gates are green.

## Gates and CI

- `pnpm test:web`
- `pnpm typecheck:web` / `pnpm lint:web`
- `pnpm test:e2e --pattern "target config"`
- `pnpm verify:flow` / `pnpm lint:docs` / `pnpm verify:docs`
- `pnpm verify:web-style` / `pnpm verify:bundle`

## Non-goals

- The `TargetConfigEntry` gear in the `/evolution` page header is a separate entry; whether to keep it is left to later feedback.
- No changes to the other wizard steps, form logic, the configuration page, or backend APIs.
