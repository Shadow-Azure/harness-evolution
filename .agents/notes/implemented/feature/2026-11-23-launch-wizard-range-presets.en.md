# Agent Note: Launch wizard time-range presets

Status: implemented

English | [中文](2026-11-23-launch-wizard-range-presets.md)

## Problem

Step 1 of the launch wizard asks the user to pick the bad-case start and end dates by hand. Common windows such as the last 7 days, last 30 days, or last half year require opening two date pickers every time, which is slow and easy to get backwards; the prototype also left no interaction baseline for the production implementation. The prototype and design docs landed first in [#536](https://github.com/Shadow-Azure/harness-evolution/pull/536); the production `LaunchWizard.vue` still had only the two date inputs and needed the same presets.

## Decision

- Put "Last 7 days / Last 30 days / Last half year" pills on the same row as the date inputs in step 1 of the V2 prototype. Clicking a preset writes concrete `from/to` values into the inputs; it does not submit a relative range or lock later editing.
- The end date is today (inclusive): last 7 days starts 6 days ago, last 30 days starts 29 days ago, and last half year starts 6 calendar months ago, clamped to the last day of the target month when needed. The prototype uses `V2_TODAY` as the demo "today"; production uses the browser's current date.
- The matching pill uses a light blue fill, blue text, and a border while the current `from/to` equals its computed range; manually changing either date clears the highlight. There is no extra "custom" state. The existing required and `from <= to` validation stays in place.
- Record the interaction in [design-v2 §7.4.1](../../../../plans/ui-prototype-v2/design-v2.md) and [08 §9 Step 1](../../../../plans/fullstack-design/08-frontend-implementation.md) as the implementation authority for the production `LaunchWizard.vue`. The prototype and design docs are merged; the production component follows the same contract.
- Extract the production date math into `launchWizardRangePresets.ts`: local calendar-day addition, half-year month-end clamping, and an `activePresetId` lookup. Compute in local calendar days rather than slicing `toISOString()` into a UTC date; the component only fills the inputs and syncs the pill state, with no new request fields.

## Alternatives considered

- Add preset entries to the browser-native date picker only: the native UI is not controllable, the prototype and production visuals would diverge, and button state cannot be tested. Rejected.
- Submit a relative range such as `range=7d`: the server would need a new field and an interpretation of "today", the run snapshot would lose the concrete window, and the existing `window: [from, to]` contract would break. Rejected.
- Add a "custom" button or a fourth mode: the date inputs already accept arbitrary values, and another mode only adds state and synchronization logic. Rejected.
- Use a fixed 180-day window instead of "last half year": the semantics and month-end boundaries differ. Rejected.
- Reuse the overview page's solid-blue segmented control: inside the wizard it carries too much visual weight, competes with the primary next button, and turns the shortcuts into a toolbar; use light pills with a tinted selected state instead. Rejected.

## Consequences

- The prototype can select a common window in one click and shows the resulting concrete dates immediately, which makes screenshot acceptance straightforward. The production `LaunchWizard.vue` mirrors the same calculation and highlight logic.
- The presets are client-side only; the API, contract, cache key, and potential-matching rules are unchanged, so production does not need backend work.
- The prototype computes from a fixed demo date, so the concrete dates in screenshots move as the demo date changes; that is a demo-data boundary, not a production default.
- Production uses the browser's local calendar day as "today"; unit tests cover 7/30 days, month and year boundaries, half-year month-end clamping, and the active lookup, while the cross-stack e2e covers filling the dates, `aria-pressed`, and clearing the highlight after a manual edit.
