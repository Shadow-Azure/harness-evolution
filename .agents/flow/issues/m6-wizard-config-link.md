# 启动向导配置入口改为提示文案内下划线链接

[English](m6-wizard-config-link.en.md) | 中文

```yaml flow
kind: issue
id: m6-10
milestone: m6
depends:
  - m5-05
priority: P1
status: done
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

## 背景

### 问题是什么

「启动自进化」向导第一步中，跳转「进化对象配置」的入口是对象选择器右侧一个独立的 `⚙` 齿轮按钮：13px 灰色裸字符、无边框无底色，视觉上与表单背景几乎融为一体；提示文案还要求用户「点击齿轮前往配置页」，把发现成本压在一个不可见的图形字符上。

### 问题现象

- 向导第一步的对象行内，齿轮按钮紧贴对象下拉右侧，用户难以注意到它是可点击入口。
- 提示文案「未配置的进化对象不会出现在列表中；点击齿轮前往配置页。」引导用户寻找一个几乎看不见的字符。
- 用户反馈：应去掉齿轮按钮，把跳转动作合并进提示文案，文案中的「配置页」可点击并加下划线。

### 问题影响

- 未配置进化对象的用户找不到配置入口，向导在空列表下无法继续，任务中断。
- 入口可发现性与可点击感不足，违反"看得出能点"的基本交互预期。

### 根因分析

- `LaunchWizard.vue` 的齿轮按钮只靠 `color: var(--text-faint)` 的 13px 字符承载可供性，无边界、无 hover 区域暗示。
- 提示文案把动作对象（齿轮）与说明文字混写，没有把可点击目标本身做成链接。
- 原型 `harness-evolution.html` 的向导第一步本无齿轮入口，应用侧自行加入后偏离了原型约定。

### 建议

- 删除齿轮按钮及其样式，向导第一步只保留表单控件。
- 提示文案改为「未配置的进化对象不会出现在列表中；点击配置页前往。」，其中「配置页」是带实线下划线的蓝色内联按钮：键盘可聚焦、focus 可见、hover 有反馈，点击沿用「关闭向导 → 跳 `/evolution/targets`」的既有行为。
- 同步原型与设计文档，使原型成为该入口的视觉权威。

## 目标

- 向导第一步不再渲染齿轮按钮，提示文案内的「配置页」是可发现、可点击、可键盘操作的链接。
- 点击行为与原入口一致：关闭向导并落在 `/evolution/targets`；返回后对象与版本候选照常刷新（沿用既有 `["catalogs"]` / `["evolution","targets"]` 失效链路）。
- 原型、设计文档、测试与实现四方一致，保留自动化回归路径。

## 设计依据

- [plans/fullstack-design/08-frontend-implementation.md §9.2](../../../plans/fullstack-design/08-frontend-implementation.md)：向导 Step1 表单与配置入口语义。
- [plans/fullstack-design/08-frontend-implementation.md §16](../../../plans/fullstack-design/08-frontend-implementation.md)：只有配置且启用的对象能启动自进化，入口在向导 Step1。
- [plans/fullstack-design/02-features.md F19](../../../plans/fullstack-design/02-features.md)：进化对象配置页功能点与入口描述。
- [plans/fullstack-design/09-review-guide.md](../../../plans/fullstack-design/09-review-guide.md)：向导 step1 → 配置页的检视对照。
- [plans/fullstack-design/README.md D13](../../../plans/fullstack-design/README.md)：进化对象配置决策条目。
- 实现冲突时以链接章节与 `plans/14-15-ui-prototype/harness-evolution.html` 原型为准。

## 实现内容

- 删除 `LaunchWizard.vue` 中对象下拉右侧的齿轮按钮及 `.gear` 样式。
- 提示文案改为含内联链接的版本，「配置页」用 `button.cfg-link`（实线下划线、`--blue`、hover 加深加重、`:focus-visible` 可见），点击复用 `goTargetConfig()`。
- 单元测试改为断言提示行内链接的存在、文案与跳转行为，并断言齿轮不存在。
- E2E「gear target config navigation」场景改为从向导提示链接进入配置页，保留自动化回归路径。
- 同步原型（`.wz-note` / `.cfg-link` 与 `wz-target-config` 分发分支）、5 处设计文档表述与 owning Agent Note。

## 实施步骤

1. 先补失败测试：单元测试断言无齿轮、提示行内 `wizard-target-config-link` 存在且点击后 `close` + 路由到 `/evolution/targets`；E2E 改为向导提示链接导航场景并看其失败。
2. 实现 `LaunchWizard.vue` 的按钮替换与 `.cfg-link` 样式，对齐原型的视觉约定。
3. 更新 E2E 场景到绿。
4. 同步原型、设计文档（08/05/02/09/README）与 owning Agent Note（中英成对 + `record:i18n`）。
5. 运行聚焦单测、前端类型与 lint、E2E、流程与文档门禁、设计 token 与 bundle 门禁。

## 依赖与交付边界

- 依赖：m5-05
- 交付边界：仅向导第一步的配置入口形态、提示文案与相应测试、原型与文档同步；不改变配置页本身与目录失效语义。

## 独立验证

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

- 向导第一步不再渲染齿轮按钮；提示行内「配置页」带下划线、键盘可聚焦，点击后向导关闭并落在 `/evolution/targets`。
- 单测、E2E、类型、lint、流程与文档门禁全绿。

## 验收标准

- 齿轮按钮（含 `.gear` 样式与无障碍命名）完全移除。
- 提示文案内「配置页」是带实线下划线的链接：hover 有反馈、键盘可操作、focus 可见、点击可跳转。
- 从配置页返回重新打开向导时，对象/版本候选照常刷新。
- 单测、E2E、文档门禁全绿。

## 门禁与 CI

- `pnpm test:web`
- `pnpm typecheck:web` / `pnpm lint:web`
- `pnpm test:e2e --pattern "target config"`
- `pnpm verify:flow` / `pnpm lint:docs` / `pnpm verify:docs`
- `pnpm verify:web-style` / `pnpm verify:bundle`

## 非目标

- 不改动 `/evolution` 页头的 `TargetConfigEntry` 齿轮入口（另一入口，是否保留由后续反馈决定）。
- 不改向导其余步骤与表单逻辑，不改配置页功能与后端接口。
