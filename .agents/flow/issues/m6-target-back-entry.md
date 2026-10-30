# 进化对象配置页：增加直接返回自进化页面的入口

[English](m6-target-back-entry.en.md) | 中文

```yaml flow
kind: issue
id: m6-14
milestone: m6
depends:
  - m5-08
priority: P1
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

从「启动自进化」向导或 `/evolution` 页头入口跳到 `/evolution/targets` 配置 skill / agent 的进化对象后，页面内没有任何返回 `/evolution` 自进化页的按钮或链接，用户只能借助顶栏导航绕回去。

### 问题现象

- 配置页 `apps/web/src/pages/evolution/targets/Index.vue` 的页头（`page-head`）只有标题「进化对象配置」与一句说明，右侧为空，没有任何返回动作。
- 入口现状：向导内跳转（`LaunchWizard.vue`）与 `/evolution` 页头的 `TargetConfigEntry` 都只有"进"没有"回"。
- 对照：其他自进化子页已有返回路径——`ClusterPreview.vue` 直接 `router.push('/evolution')`，`RunDetail.vue` 有 `RouterLink` 返回；唯独配置页缺失。

### 问题影响

- 配置完对象后想回到自进化页启动向导，只能点顶栏导航绕行，多一步且路径不直观。
- 与 ClusterPreview / RunDetail 的既有返回约定不一致，页面间导航心智不统一。

### 根因分析

- 配置页骨架从未包含返回入口；原型 `harness-evolution.html` 的 targets 页在标题上方有「← 返回自进化列表」小字链接，实现时遗漏了这一元素。

### 建议

- 在配置页内容最上方加 `RouterLink to="/evolution"` 的「← 返回自进化」链接，样式与 `RunDetail.vue` 的 `.back` 一致；显式 `to` 而非 `router.back()`，直达、刷新、新标签打开时行为可预期。

## 目标

- 配置页在任意状态下（有数据、空态、读取失败）都能一键回到 `/evolution`。
- 入口有可访问名称与 focus 态，键盘可达。
- 相关单测全绿，文档门禁不受影响。

## 设计依据

- [plans/14-15-ui-prototype/harness-evolution.html](../../../plans/14-15-ui-prototype/harness-evolution.html)：targets 页原型，返回链接位于标题上方。
- [plans/fullstack-design/08-frontend-implementation.md](../../../plans/fullstack-design/08-frontend-implementation.md)：配置页路由与页面归属。
- `apps/web/src/pages/evolution/RunDetail.vue`：既有 `.back` 返回链接先例。

## 实现内容

- `targets/Index.vue` 内容最上方加 `RouterLink to="/evolution"`（文案「← 返回自进化」，`data-testid="target-config-back"`），样式与 RunDetail `.back` 一致（12px 灰字、hover/focus 变蓝）。
- 单测：断言链接存在、`props("to") === "/evolution"`，点击后路由落地 `/evolution`。
- E2E `m5-target-config`：末尾点击返回入口，断言落在 `/evolution`。
- 同步 owning Agent Note（中英成对 + 配对记录）。

## 实施步骤

1. 先补失败测试：单测断言返回入口存在且点击后路由变为 `/evolution`；E2E 补"配置页点击返回落在 `/evolution`"断言。
2. 实现 `targets/Index.vue` 返回入口与样式。
3. 更新单测与 E2E 到绿。
4. 同步 owning Agent Note（中英成对 + 配对记录）。
5. 运行聚焦单测、前端类型与 lint、E2E、流程与文档门禁。

## 依赖与交付边界

- 依赖：m5-08
- 交付边界：仅配置页返回入口及相应测试与文档同步；不改配置页 CRUD 行为与表格交互；不为 ClusterPreview / RunDetail 等已有返回路径的页面重复添加。

## 独立验证

```sh
pnpm test:web -- targets
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- "m5 target"
pnpm verify:flow
pnpm lint:docs
```

- 渲染配置页，断言返回链接存在且 `to` 为 `/evolution`；点击后当前路由变为 `/evolution`。
- 上述门禁全绿。

## 验收标准

- 配置页在任意状态下都能一键回到 `/evolution`。
- 入口有可访问名称与 focus 态，键盘可达。
- 单测、E2E、类型、lint、流程与文档门禁全绿。

## 门禁与 CI

- `pnpm test:web`
- `pnpm typecheck:web` / `pnpm lint:web`
- `pnpm test:e2e -- "m5 target"`
- `pnpm verify:flow` / `pnpm lint:docs` / `pnpm verify:docs`

## 非目标

- 不改配置页 CRUD 行为与表格交互。
- 不为 ClusterPreview / RunDetail 等已有返回路径的页面重复添加返回入口。
- 不改路由结构与守卫逻辑。
