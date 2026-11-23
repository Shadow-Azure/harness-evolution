# Launch wizard time range: last 7 days, 30 days, and half year presets

English | [中文](bugfix-launch-wizard-range-presets.md)

```yaml flow
kind: issue
id: bugfix-30
milestone: bugfix
depends:
  - m10-05
priority: P2
status: in-progress
scope:
  - plans/ui-prototype-v2/**
  - plans/fullstack-design/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 535
  url: https://github.com/Shadow-Azure/harness-evolution/issues/535
```

## Background

### Problem scenario

On 2026-11-23 a user reported that step 1 of "Launch evolution" still requires two manual date-picker selections for the bad-case time range. Common windows such as the last 7 days, last 30 days, or last half year are re-entered every time; it is slow and easy to reverse the start and end dates. The user asked for three presets in the prototype first, with the concrete dates filled in on click, and for the request, before/after prototype screenshots, and solution to be recorded in an issue while the PR also updates the design docs.

The current prototype (baseline `main@d33b2c45`) has only two native date inputs in step 1, defaulting to `2026-10-01 ~ 2026-11-09`, with no shortcut above them:

![Prototype before: step 1 of the launch wizard has only two date inputs and no range shortcut (baseline main@d33b2c45)](https://github.com/Shadow-Azure/harness-evolution/releases/download/launch-wizard-range-presets-evidence-20261123/before-wizard1-v3.png)

### Observations

- The range filters bad cases by `created_at`, and the end date is usually today; every common window can be derived from "today" plus a fixed number of days or months.
- The range is a closed interval and the existing validation requires `from <= to`; a shortcut may only reduce typing, not change the filter semantics, request fields, or later Session association.
- The prototype fixes its demo date at `V2_TODAY = 2026-11-10` and all demo data is built around that day; the shortcut's "today" must match this demo date, or the concrete dates in screenshots will not line up with the page data.
- The V2 overview page already uses a segmented "last 7 / 30 / 90 days" control; the wizard borrows only the "single-choice common range" information structure. Visually it uses light pills with a tinted selected state, so the shortcuts do not become a second toolbar, and it does not copy the overview's grain linkage.

### Impact

- No impact on the backend, API, contract, or run snapshot; this is a step-1 input-experience problem.
- Production `LaunchWizard.vue` still has only two date inputs; this issue delivers a comparable prototype and the design contract first, and production implementation stays for a separate slice.

## Goals

- Add "Last 7 days / Last 30 days / Last half year" pills on the same row as the date inputs in step 1 of the launch wizard.
- On click, write concrete `from/to` values into the date inputs: the end date is today (inclusive), last 7 days starts 6 days ago, last 30 days starts 29 days ago, and last half year starts 6 calendar months ago.
- Highlight the matching pill with a light blue fill and blue text while the current range equals its computed values; clear the highlight when the user manually changes either date. Do not add an extra "custom" state.
- Keep the existing required and `from <= to` validation and request fields unchanged; record the interaction in the V2 design doc and the 08 frontend design doc as the production authority.

## Design authority

- [08 §9 Launch wizard Step 1](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L669): the `from/to` range is required and validates `from <= to`; this issue adds the shortcut contract to that line.
- [V2 design §7.4.1 Time-range presets](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/design-v2.md#L223): records the calculation, fill-only behavior, unchanged validation, and accessibility.
- [Four-step launch wizard and condition snapshot](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/feature/2026-11-17-four-step-launch-wizard.md): step 1 is the only condition-editing surface; changing the object, version, range, or policy invalidates later previews.
- [V2 prototype entry](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/index.html): `harness-evolution.html?u=admin&page=evo&demo=wizard1` opens step 1 directly, which keeps screenshots on the same scenario.
- [AppSignal Date and time filter](https://appsignal.design/patterns/date-time-filter.html): presets are single-choice relative ranges with a clear selected state, separate from the custom range; this issue keeps that information structure and uses light pills with a tinted selected state.
- [Grafana quick time ranges](https://grafana.com/whats-new/2025-06-17-server-configurable-quick-time-ranges-for-dashboards/): common ranges come first and stay lightweight; this issue does not add a relative-range protocol.

## Implementation

### Prototype interaction

- Put three pills on the same row as the date inputs in step 1 of `plans/ui-prototype-v2/harness-evolution.html`, separated from the dates by a thin vertical rule; the group uses `role=group`, the current pill sets `aria-pressed`, and the selected state is a light blue fill with blue text and a border.
- Add `EV_WZ_RANGE_PRESETS` and date helpers that compute concrete ranges from the prototype demo date `V2_TODAY`:

| Preset | Calculation | Prototype example (V2_TODAY = 2026-11-10) |
|---|---|---|
| Last 7 days | `today - 6` ~ `today` | `2026-11-04 ~ 2026-11-10` |
| Last 30 days | `today - 29` ~ `today` | `2026-10-12 ~ 2026-11-10` |
| Last half year | `today - 6 calendar months` ~ `today` | `2026-05-10 ~ 2026-11-10` |

- A click only updates `wz.from` / `wz.to`, the two input values, and the pill state; it does not rebuild the form, so focus stays on the clicked pill. A manual date change recomputes the match and clears all highlights when no preset matches.
- For last half year, month-end dates clamp to the last day of the target month (for example, 6 months before August 31 lands on the last day of February); both ends participate as a closed interval.
- The change is client-side only: no new request field, no change to `from <= to` validation, Session association, potential-matching semantics, or cache keys.

After the prototype change (same scenario, 1500×900 viewport, light theme, `u=admin&page=evo&demo=wizard1`):

**Last 30 days selected; dates become 2026-10-12 ~ 2026-11-10**

![Prototype after: clicking Last 30 days fills 2026-10-12 ~ 2026-11-10](https://github.com/Shadow-Azure/harness-evolution/releases/download/launch-wizard-range-presets-evidence-20261123/after-30d-v3.png)

**Last 7 days selected; dates become 2026-11-04 ~ 2026-11-10**

![Prototype after: clicking Last 7 days fills 2026-11-04 ~ 2026-11-10](https://github.com/Shadow-Azure/harness-evolution/releases/download/launch-wizard-range-presets-evidence-20261123/after-7d-v3.png)

**Last half year selected; dates become 2026-05-10 ~ 2026-11-10**

![Prototype after: clicking Last half year fills 2026-05-10 ~ 2026-11-10](https://github.com/Shadow-Azure/harness-evolution/releases/download/launch-wizard-range-presets-evidence-20261123/after-6m-v3.png)

### Design docs and decision record

- Add §7.4.1 to `plans/ui-prototype-v2/design-v2.md` with the calculation, fill-only behavior, demo-date boundary, and accessibility.
- Add the same interaction contract to the "time range" bullet under §9 Step 1 of `plans/fullstack-design/08-frontend-implementation.md` as the production `LaunchWizard.vue` authority.
- Add the Agent Note `2026-11-23-launch-wizard-range-presets` to explain why a relative range is not sent to the server, why there is no "custom" button, and why a fixed 180-day window is not used.

## Implementation steps

1. Add the pill shortcuts, date helpers, active highlight, and click handler to prototype step 1.
2. Update `design-v2.md` §7.4.1 and `08-frontend-implementation.md` §9 Step 1.
3. Add the bilingual Agent Note and rerun `pnpm record:i18n -- <pair>`.
4. Capture before/after screenshots in the same browser scenario, upload them to an evidence Release, and keep them out of the repository.
5. Run the syntax check, `pnpm verify:flow`, and `pnpm lint:docs`; confirm the PR title contains `(#<issue>)`.
6. Open the prototype PR with before/after evidence and verification notes; a person merges it.

## Related PR

- Prototype and design-doc PR: [#536](https://github.com/Shadow-Azure/harness-evolution/pull/536)

## Dependencies and boundary

- Depends on m10-05 (four-step launch wizard, done); this issue only improves the step-1 range input and does not change the four-step state machine.
- Delivery boundary: `plans/ui-prototype-v2/**`, `plans/fullstack-design/**`, `.agents/**`, and the PR self-review record.
- Do not modify the production `LaunchWizard.vue` under `apps/web`, `apps/api`, `packages/contracts`, or the database; production work needs a separate issue.
- Screenshots live as Release evidence and do not enter the repository; do not expose production run IDs, Session content, or credentials.

## Verification

```sh
python3 - <<'PY'
import re
from pathlib import Path
html = Path("plans/ui-prototype-v2/harness-evolution.html").read_text()
scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, re.S)
Path(".tmp-proto-main.js").write_text(scripts[-1])
PY
node --check .tmp-proto-main.js
rm .tmp-proto-main.js
pnpm verify:flow
pnpm lint:docs
```

- Open `plans/ui-prototype-v2/harness-evolution.html?u=admin&page=evo&demo=wizard1` in Chrome at 1500×900 in the light theme.
- The initial dates are `2026-10-01 ~ 2026-11-09` and no shortcut is highlighted. Clicking "Last 30 days" changes the inputs to `2026-10-12 ~ 2026-11-10` with only that pill highlighted; "Last 7 days" and "Last half year" produce `2026-11-04 ~ 2026-11-10` and `2026-05-10 ~ 2026-11-10`.
- After manually changing the end date to `2026-11-09`, no shortcut is highlighted; clicking "Next: associate Sessions" still runs the original required and `from <= to` validation.
- See the evidence above; the before image is baseline `main@d33b2c45`, and the after images come from this issue's branch.

## Acceptance

- Step 1 shows three pills ("Last 7 days / Last 30 days / Last half year") on the same row as the date inputs, with none selected by default.
- Clicking a shortcut immediately fills both dates, ending today (inclusive); the three example ranges match the table, and last half year clamps at month ends.
- The matching pill is highlighted with `aria-pressed=true`; manually changing a date clears the highlight; there is no extra "custom" button.
- Existing required and `from <= to` validation, next-step previews, and request fields are unchanged; the page has no horizontal scroll and the modal height and button positions stay usable.
- `design-v2.md` and `08-frontend-implementation.md` state the same contract, and the Agent Note is bilingual with a refreshed pairing record.
- The issue contains the before screenshot, after screenshots, and the solution; the PR description contains same-scenario, same-viewport, same-theme Before / After evidence.
- The requester accepts the interaction: the issue stays open until the requester confirms the prototype matches expectations.

## Gates and CI

- `pnpm verify:flow`: flow tree, dependencies, body sections, and state machine.
- `pnpm verify:flow --diff origin/main`: PR title contains `(#<issue>)`, issue eligibility, and diff scope coverage.
- `pnpm lint:docs`: Agent Note pairing, paragraph wrapping, and doc gates.
- The PR only changes the prototype and design docs, so it does not run `apps/web` / `apps/api` tests; the CI static lane must still be green.
- A person merges this PR; do not enable auto-merge.

## Non-goals

- Do not change the production `LaunchWizard.vue` under `apps/web`, and do not require production UI in this PR.
- Do not change the backend, API, contract, database, Session association, potential-matching policy, or cache keys.
- Do not rearrange other step-1 fields, the version combo box, the policy radios, the step strip, or later steps.
- Do not introduce a new date library, change native date-control behavior, or start a timezone/localization project.
- Do not submit a relative range to the backend, add a "custom" mode, or change the closed-interval semantics.
- Do not commit screenshots or production data, and do not expose production run IDs, Session content, or credentials in the issue.
