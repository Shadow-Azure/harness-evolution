# 启动向导：下一步恒可点并内联必填校验，空命中进第二步空态

[English](m6-wizard-validation-empty-state.en.md) | 中文

```yaml flow
kind: issue
id: m6-13
milestone: m6
depends:
  - m5-05
priority: P1
status: done
scope:
  - apps/web/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
  - reports/**
adr: []
github:
  number: 161
  url: https://github.com/Shadow-Azure/harness-evolution/issues/161
```

## 背景

### 问题是什么

「启动自进化」向导第一步把全部校验压在「下一步：查询匹配报告」按钮的禁用态上：`LaunchWizard.vue` 用 `:disabled="!selectedTarget || !targetVersion || windowInvalid()"` 直接禁用按钮，用户不知道为什么不能点；而时间段标了必填 `*` 却不参与禁用判断，形成"有时灰、有时可点"的不一致。条件填齐后若零命中，后端 `probes/query` 返回 `409 NO_PROBES_MATCHED`，前端把原始英文 message 直接显示在第一步底部，流程终止在第一步。

### 问题现象

- 未选对象或版本时「下一步」按钮灰掉，点击无任何解释；时间段未填时按钮却可以点，必填标 `*` 与禁用规则互相矛盾。
- 对象、版本、时间段都填了但命中为 0 时，第一步底部出现红色英文「no analyzed probe matches the wizard condition」，无法进入第二步，也没有"调整条件"的引导。
- 单测 `LaunchWizard.test.ts` 直接断言按钮的 `disabled` 属性（初始未选对象、区间倒挂等场景），把禁用态固化成了预期行为。

### 问题影响

- 用户在空表单上找不到"该填什么"的指向，必填反馈依赖猜测，向导第一步的可用性受损。
- 零命中被当成错误终点：用户看到内部英文文案、停留在第一步，与"查询成功但没有结果"的真实语义不符。

### 根因分析

- `runQuery()` 只在 `!selectedTarget || windowInvalid()` 时静默 `return`，没有字段级反馈通道；按钮禁用是唯一的校验表达。
- 原型 `harness-evolution.html` 的 `wz-query` 按钮本无 disabled 态，应用侧自行加入禁用偏离了原型约定。
- 前端把 `409 NO_PROBES_MATCHED` 与其他错误一视同仁地塞进 `previewError`，没有兑现 `05-api-design.md §4.9` 规定的"结果为空"业务空态映射。

### 建议

- 「下一步」恒可点；点击时做字段级必填校验：进化对象、版本、时间段起止缺失时对应输入框标红并在框下显示红色「缺失必填字段」类提示，区间倒挂沿用既有文案并同样标红；字段修正后错误态即时清除。
- 零命中视为查询成功但结果为空：进入第二步渲染空态（未找到匹配的问题报告/probe + 调整条件引导），两个出口按钮在空态禁用；其余错误仍在第一步提示。
- 同步原型、设计文档与测试，使四方一致。

## 目标

- 「下一步：查询匹配报告」按钮始终可点；点击时校验必填：进化对象、版本、时间段起止缺失（或区间倒挂）不进入第二步，对应输入框标红并在框下显示红色提示，字段修正后错误态即时清除。
- 零命中（`409 NO_PROBES_MATCHED`）进入第二步：显示"未找到匹配的问题报告"空态与调整条件引导；两个出口按钮在空态禁用；其余错误仍在第一步红色提示。
- 原型、设计文档、测试与实现四方一致，保留自动化回归路径。

## 设计依据

- [plans/fullstack-design/08-frontend-implementation.md §9.1](../../../plans/fullstack-design/08-frontend-implementation.md)：状态机 Step1→Step2 以"条件校验通过"为迁移条件。
- [plans/fullstack-design/08-frontend-implementation.md §9.2](../../../plans/fullstack-design/08-frontend-implementation.md)：Step1 表单与「下一步」行为（点击时字段级校验；`409 NO_PROBES_MATCHED` 映射到 Step2 空态）。
- [plans/fullstack-design/08-frontend-implementation.md §9.3](../../../plans/fullstack-design/08-frontend-implementation.md)：Step2 命中确认与两个出口。
- [plans/fullstack-design/05-api-design.md §4.9](../../../plans/fullstack-design/05-api-design.md)：`409 NO_PROBES_MATCHED` 的口径与前端空态映射。
- [plans/fullstack-design/09-review-guide.md](../../../plans/fullstack-design/09-review-guide.md)：向导 step1→step2 检视对照行。
- [plans/14-15-ui-prototype/harness-evolution.html](../../../plans/14-15-ui-prototype/harness-evolution.html)：向导原型，`wz-query` 按钮无 disabled 态。
- 实现冲突时以链接章节与 `plans/14-15-ui-prototype/harness-evolution.html` 原型为准。

## 实现内容

- 移除 `wizard-next` 的 `:disabled`；`runQuery()` 点击时校验：`selectedTarget` 非空、`targetVersion` 非空、`windowFrom`/`windowTo` 非空、`from <= to`。
- 校验失败时：缺失字段输入框加红色边框（`aria-invalid` + 样式类），并在对应框下方显示红色提示（「请选择进化对象」「请选择版本」「请选择时间段」等缺失必填字段文案）；区间倒挂沿用「起始时间不能晚于结束时间」并同样标红；任一字段输入/修改后清除该项错误态；校验失败不发请求、不进入第二步。
- `runQuery()` 捕获 `409 NO_PROBES_MATCHED` 时视为空结果：`step = 2` 渲染空态面板（未找到匹配的问题报告/probe 的说明与「修改条件」引导），条件摘要条保留，「启动自进化」与「启动问题聚类分析」按钮禁用（后端 launch 同口径会 409）；其他错误保持第一步 `wizard-error` 展示。
- 单元测试：删除对 `wizard-next` `disabled` 属性的断言，新增"按钮恒可点""缺失必填逐字段标红 + 框下提示 + 不发请求""输入后错误清除""`NO_PROBES_MATCHED` 进第二步空态且出口禁用"用例；"conflicts when no probe matches and stays on step 1" 场景改写为新行为。
- E2E `m5-05-launch-wizard` 同步空态与校验场景。
- 同步原型（校验错误态与空态演示分支）、设计文档（05 §4.9 / 08 §9.2–9.3 / 09 检视行）与 owning Agent Note（中英成对 + `record:i18n`）。

## 实施步骤

1. 先补失败测试：单测断言按钮永不禁用；空对象/空版本/空时间段点击 → 各框标红 + 框下提示且无请求发出；`409 NO_PROBES_MATCHED` → 进入第二步空态、出口按钮禁用；E2E 场景同步改写并看其失败。
2. 实现 `LaunchWizard.vue` 的字段级校验与 `NO_PROBES_MATCHED` → 空态映射。
3. 更新单元测试与 E2E 到绿。
4. 同步原型、设计文档（05/08/09）与 owning Agent Note（中英成对 + `record:i18n`）。
5. 运行聚焦单测、前端类型与 lint、E2E、流程与文档门禁、设计 token 与 bundle 门禁。

## 依赖与交付边界

- 依赖：m5-05
- 交付边界：仅向导第一步的必填校验反馈、下一步→第二步的空命中流转及相应测试、原型与文档同步；不改后端 409 契约与 launch 校验。

## 独立验证

```sh
pnpm --filter @harness/web test -- LaunchWizard
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e --pattern m5-05
pnpm verify:flow
pnpm lint:docs
pnpm verify:web-style
pnpm verify:bundle
```

- 打开向导直接点「下一步」：对象/版本/时间段标红并在框下显示红色提示，无网络请求；逐项填写后错误态清除。
- 填齐条件后查询零命中：进入第二步，显示未匹配空态，两个出口按钮禁用，「修改条件」可返回第一步。
- 上述门禁全绿。

## 验收标准

- `wizard-next` 无任何 disabled 态，任意表单状态下都可点击。
- 缺失必填字段逐字段标红 + 框下红色提示；字段输入后该项错误即时清除；区间倒挂沿用既有文案并标红。
- 零命中进入第二步：显示"未找到匹配的问题报告"空态与调整条件引导，两个出口按钮禁用；非 `NO_PROBES_MATCHED` 错误仍在第一步提示。
- 单测、E2E、类型、lint、流程与文档门禁全绿。

## 门禁与 CI

- `pnpm test:web`
- `pnpm typecheck:web` / `pnpm lint:web`
- `pnpm test:e2e --pattern m5-05`
- `pnpm verify:flow` / `pnpm lint:docs` / `pnpm verify:docs`
- `pnpm verify:web-style` / `pnpm verify:bundle`

## 非目标

- 不改 `probes/query`、`runs`、`cluster-previews` 的 409 契约与 OpenAPI。
- 不改模型多选语义（全不选 = 全部模型）与版本必填口径（后端 `defaultRef` 兜底不变）。
- 不重构向导其余步骤与表单逻辑，不改配置页与目录失效语义。
