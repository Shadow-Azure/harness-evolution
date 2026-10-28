# Fix evolution target baseline ref input and tag loading

English | [中文](m6-target-ref-input.md)

```yaml flow
kind: issue
id: m6-07
milestone: m6
depends:
  - m5-03
priority: P1
status: ready
scope:
  - apps/web/**
  - apps/api/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - docs/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 153
  url: https://github.com/Shadow-Azure/harness-evolution/issues/153
```

## Background

### What the problem is

The create-target dialog renders `defaultRef` as a filterable, creatable `ElSelect`, but typed text only updates the component's internal filter state. The form `v-model` changes only after the user presses Enter or clicks the generated create option; moving focus away or clicking “新增配置” discards the typed branch or tag and triggers the required-field error.

A new target has no target id, while `GET /api/evolution/targets/{targetId}/versions` can only query a saved target. The dialog therefore never requests repository tags, yet treats the disabled query's `isPending` state as loading and keeps showing “正在读取仓库版本…”. The backend accepts both branches and tags, while the versions endpoint returns tags only, and the create state cannot obtain any remote suggestions.

### Symptoms

- Opening “新增进化对象” shows an empty baseline dropdown with a persistent “正在读取仓库版本…” message.
- Typing `main`, `feature/foo`, or `v2.0.0` and then clicking another field or “新增配置” loses the value and shows “请填写基线分支或标签”.
- The value is retained only when the user presses Enter or clicks the temporary create option in the dropdown.
- Editing a saved target loads tags from that target's saved repository, but the current branch appears only because it is added as an extra option; after changing the repository URL, suggestions still come from the old repository until save and refetch.

### Impact

- Administrators following normal text-input behavior cannot create a target and may conclude that the field is read-only or the repository is unavailable.
- The page promises a branch or tag, but neither branches nor tags are discoverable during creation. Users must enter a value from memory before the page can offer suggestions.
- Existing component tests emit `update:modelValue` directly on `ElSelect`, bypassing real typing and blur, so they miss the regression.

### Root cause

- `TargetFormDialog.vue` uses `ElSelect` with `filterable + allow-create`, but its form model does not update from the typed text. Element Plus commits the model only when an option is selected; blur closes the dropdown and clears the internal filter text.
- `Index.vue` enables the versions query only when `editingTarget` has an id. The create state has no id, and the backend endpoint requires a target id.
- TanStack Query reports a disabled query as `status=pending`, while the page uses `isPending` instead of actual fetch state. The create dialog therefore appears to load forever.
- The backend validates saves with `git ls-remote <repo> <ref>`, accepting resolvable branches or tags, while version reads use `git ls-remote --tags` and return tags only.

### Recommendation

- Make the baseline field an input-first editable combobox. Typed text is the submitted value; entering a suggestion list or selecting a tag is optional assistance. Current text must survive blur and form submission.
- Keep Enter and option clicks as shortcuts, but never require them for ordinary input.
- Do not fake remote tag loading during creation. Allow a branch or tag to be entered before the target is saved and explain that tag suggestions become available after a repository is configured. If pre-save tag suggestions are needed later, add a controlled backend query boundary rather than probing repositories from the browser or exposing arbitrary `repoUrl` probes to ordinary authenticated users.
- Show loading only while a request is actually fetching, not for a disabled pending query.
- Test real typing, blur, and submit. Cover create with no target id, edit-mode tag suggestions, a current branch absent from tags, and input preservation after 422.

## Goals

- A new target can save any valid remote branch or tag entered as ordinary text without an implicit selection or Enter press.
- The create state no longer shows unsupported version loading, while edit mode still offers tags from the saved repository.
- Input, suggestions, submission, and error preservation have consistent semantics covered by real DOM interaction tests.

## Design authority

- [plans/fullstack-design/08-frontend-implementation.md §9.5](../../../plans/fullstack-design/08-frontend-implementation.md#95-进化对象配置页evolutiontargets): the baseline is a branch or tag, and version suggestions come from repository tags.
- [plans/fullstack-design/05-api-design.md §4.11](../../../plans/fullstack-design/05-api-design.md#411-进化对象配置仅配置后可自进化): create accepts a branch or tag, and the versions endpoint reads tags by target id.
- If these descriptions conflict with implementation, the current backend `GitRemote` validation semantics take precedence.

## Implementation

- Adjust the baseline control so typed text is a controlled form value and remote tags remain optional suggestions.
- Synchronize the value on blur and before form submission so direct typing survives moving to another control or submitting.
- Correct version-query and loading behavior in create mode: show loading only when a target id exists and a request is actually fetching.
- Preserve edit-mode tag suggestions and current `defaultRef` visibility, including branches absent from the tag list.
- Update the relevant design guidance and add an Agent Note explaining the input-first, suggestions-second model and the create-mode remote-suggestion boundary.

## Implementation steps

1. Add failing tests for real typing followed by blur, direct submit after typing, no versions request in create mode, no create-mode loading, and tag suggestions in edit mode.
2. Synchronize the baseline control's typed value into form state before any suggestion selection.
3. Tighten the version-query loading condition to a real fetch with a target id.
4. Update frontend implementation guidance and the Agent Note with the create-versus-saved suggestion boundary.
5. Run focused unit tests, frontend types and lint, flow gates, documentation gates, and target-config E2E.

## Dependencies and boundary

- Dependency: m5-03
- Delivery boundary: fix baseline input semantics, create-mode version suggestion loading, and related tests on the configuration page; do not change backend `git ls-remote` branch/tag validation.

## Verification

```sh
pnpm --filter @harness/web exec vitest run src/pages/evolution/targets/components/TargetFormDialog.test.ts src/pages/evolution/targets/Index.test.ts src/composables/useEvolutionTargets.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- "m5 target configuration"
pnpm verify:flow
pnpm verify:docs
```

- New tests type a branch and then blur or submit, asserting the request body retains the complete `defaultRef`.
- Create mode makes no versions request and does not keep showing loading; edit mode still shows tag suggestions and the current branch.
- After 422 `REPO_INVALID`, the form remains open and all input is preserved.
- Frontend types, lint, flow, documentation, and target-config E2E all pass.

## Acceptance

- In “新增进化对象”, entering `main`, `feature/foo`, or `v2.0.0`, moving to another field, and clicking “新增配置” sends the normalized value in the request body.
- A valid branch or tag can be saved without pressing Enter or clicking the dropdown's create option.
- Create mode does not show “正在读取仓库版本…” or infinite loading; loading appears only during a real versions request.
- Editing a target still allows tag selection, and a current branch absent from tags remains visible and can be saved.
- Missing or unreachable refs still return `REPO_INVALID`; the error stays inside the form and all input remains.
- Component tests cover real typing and blur paths instead of only emitting `update:modelValue`.

## Gates and CI

- `pnpm test:web`
- `pnpm typecheck:web`
- `pnpm lint:web`
- `pnpm test:e2e -- "m5 target configuration"`
- `pnpm verify:flow`
- `pnpm lint:docs` / `pnpm verify:docs`

## Non-goals

- Do not change backend security validation for branches, tags, repository URLs, or subdirectories.
- Do not add arbitrary unsaved-`repoUrl` probing for ordinary authenticated users.
- Do not require remote tag selection or change version selection in the launch wizard.
- Do not refactor the entire target configuration page or launch workflow.
