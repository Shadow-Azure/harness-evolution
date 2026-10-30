# Target config page: add a direct entry back to the evolution page

English | [中文](m6-target-back-entry.md)

```yaml flow
kind: issue
id: m6-14
milestone: m6
depends:
  - m5-08
priority: P2
status: in-progress
scope:
  - apps/web/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
  - reports/**
adr: []
github:
  number: 151
  url: https://github.com/Shadow-Azure/harness-evolution/issues/151
```

## 背景

### 问题是什么

After jumping to `/evolution/targets` from the launch wizard or the `/evolution` page head to configure skill / agent evolution targets, the page offers no button or link back to `/evolution`; users must detour through the top navigation.

### 问题现象

- The config page header (`page-head`) in `apps/web/src/pages/evolution/targets/Index.vue` only has the title「进化对象配置」and one note line; the right side is empty, with no back action.
- Entry points today: the wizard jump (`LaunchWizard.vue`) and the `TargetConfigEntry` on the `/evolution` page head only go "in", never "back".
- Comparison: other evolution subpages already have return paths — `ClusterPreview.vue` calls `router.push('/evolution')`, `RunDetail.vue` has a `RouterLink` back link; only the config page lacks one.

### 问题影响

- After configuring targets, returning to the evolution page to launch a run requires a detour through the top navigation — an extra step with an unintuitive path.
- Inconsistent with the existing return conventions of ClusterPreview / RunDetail, fragmenting page navigation mental models.

### 根因分析

- The config page skeleton never included a back entry; the prototype `harness-evolution.html` has a small「← 返回自进化列表」link above the title on its targets page, and the implementation missed that element.

### 建议

- Add a `RouterLink to="/evolution"` link labelled「← 返回自进化」at the top of the config page content, styled like the `.back` link in `RunDetail.vue`; an explicit `to` instead of `router.back()` stays predictable on direct entry, refresh, and new tabs.

## 目标

- The config page can return to `/evolution` in one click in any state (data, empty, read failure).
- The entry has an accessible name and a focus state, keyboard reachable.
- Related unit tests stay green; documentation gates unaffected.

## 设计依据

- [plans/14-15-ui-prototype/harness-evolution.html](../../../plans/14-15-ui-prototype/harness-evolution.html): targets page prototype, back link above the title.
- [plans/fullstack-design/08-frontend-implementation.md](../../../plans/fullstack-design/08-frontend-implementation.md): config page routing and page ownership.
- `apps/web/src/pages/evolution/RunDetail.vue`: existing `.back` link precedent.

## 实现内容

- Add `RouterLink to="/evolution"` at the top of `targets/Index.vue` (label「← 返回自进化」, `data-testid="target-config-back"`), styled like RunDetail's `.back` (12px dim text, hover/focus blue).
- Unit test: assert the link exists with `props("to") === "/evolution"`, and clicking lands the route on `/evolution`.
- E2E `m5-target-config`: click the back entry at the end and assert landing on `/evolution`.
- Sync the owning Agent Note (bilingual pair + pairing record).

## 实施步骤

1. Add failing tests first: unit test asserts the back entry exists and clicking changes the route to `/evolution`; E2E adds a "click back on config page lands on `/evolution`" assertion.
2. Implement the back entry and styles in `targets/Index.vue`.
3. Bring unit and E2E tests back to green.
4. Sync the owning Agent Note (bilingual pair + pairing record).
5. Run focused unit tests, web typecheck and lint, E2E, flow and docs gates.

## 依赖与交付边界

- 依赖：m5-08
- 交付边界：only the config page back entry plus its tests and doc sync; no changes to config page CRUD behavior or table interactions; no duplicated back entries for pages that already have them (ClusterPreview / RunDetail).

## 独立验证

```sh
pnpm test:web -- targets
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- "m5 target"
pnpm verify:flow
pnpm lint:docs
```

- Render the config page, assert the back link exists with `to` `/evolution`; clicking changes the current route to `/evolution`.
- All gates above green.

## 验收标准

- The config page returns to `/evolution` in one click in any state.
- The entry has an accessible name and a focus state, keyboard reachable.
- Unit, E2E, typecheck, lint, flow and docs gates all green.

## 门禁与 CI

- `pnpm test:web`
- `pnpm typecheck:web` / `pnpm lint:web`
- `pnpm test:e2e -- "m5 target"`
- `pnpm verify:flow` / `pnpm lint:docs` / `pnpm verify:docs`

## 非目标

- 不改配置页 CRUD 行为与表格交互。
- 不为 ClusterPreview / RunDetail 等已有返回路径的页面重复添加返回入口。
- 不改路由结构与守卫逻辑。
