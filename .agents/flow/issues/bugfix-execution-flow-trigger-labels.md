# 执行流主链的 subagent 触发节点显示任务描述，未显示 skill/subagent 名称

[English](bugfix-execution-flow-trigger-labels.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-04
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - apps/web/**
  - plans/ui-prototype-v2/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 439
  url: https://github.com/Shadow-Azure/harness-evolution/issues/439
```

## 背景

2026-11-20，用户在生产「Session 错误查看」页核对执行流主链的触发节点标签，问这里显示的到底是 skill 还是 subagent 的名称。截图对应的生产 Session 是 `90e6c9f9-6f2e-4f7b-b313-a616993975e5`（工作空间 `OpenSpec-cn_SWE-bench`，bad case `[SWE-bench] astropy__astropy-13579 · not_scored`）；红框标注的是结构树主链里 6 个紫色菱形节点，文字依次是 “Implement sliced WCS …”“Spec compliance revie…”“Add towncrier changel…”“Code quality review o…”“Verify fix and check …”“Final rev…”。

生产全页截图（红框为用户标注的核对位置）：

![生产「Session 错误查看」执行流主链](https://github.com/Shadow-Azure/harness-evolution/releases/download/execution-flow-label-evidence-20261120/shot.jpg)

标签放大：

![生产执行流主链：6 个 subagent 触发节点显示任务描述](https://github.com/Shadow-Azure/harness-evolution/releases/download/execution-flow-label-evidence-20261120/prod-labels.jpg)

生产 Session 的原始数据（`GET /api/workspaces/{wid}/sessions/{sid}/tree`）显示，这 6 个事件全部是 `kind: "agent"`，`name` 与 `desc` 分开存放：

| 行 | `event.name`（subagent 名称） | `event.desc`（任务描述） | 链上显示 |
|---:|---|---|---|
| 369 | `code-generator` | Implement sliced WCS world_to_pixel fix | Implement sliced WCS … |
| 386 | `spec-reviewer` | Spec compliance review of task 1 | Spec compliance revie… |
| 387 | `code-generator` | Add towncrier changelog fragment | Add towncrier changel… |
| 398 | `code-quality-reviewer` | Code quality review of the fix | Code quality review o… |
| 492 | `code-generator` | Verify fix and check regressions | Verify fix and check … |
| 510 | `code-quality-reviewer` | Final review of overall implementation | Final rev… |

## 核对结论：V2 原型这里写的是什么

V2 原型 `plans/ui-prototype-v2/harness-evolution.html` 的结构树主链使用同一分支（`chainOf`）：

```js
const text = e.kind === "skill"
  ? (e.name || "skill")
  : clipName(e.desc || e.name || e.kind);
```

- **skill 触发**：绿色菱形节点显示 `event.name`，即 skill 名称（原型样例是 `deep-research`、`superpowers:dispatching-parallel-agents`）。
- **subagent 触发**：紫色菱形节点显示 `event.desc || event.name`，即任务描述（原型样例是 `检索模型层三方法`、`检索EverMind与Hermes` 等）；subagent 的类型/名称显示在下方子 agent 卡片上，如 `general-purpose · 检索模型层三方法 · L33`。

V2 原型结构树（同一句 `chainOf`；绿色是 skill 名称，紫色是 subagent 描述）：

![V2 原型结构树主链](https://github.com/Shadow-Azure/harness-evolution/releases/download/execution-flow-label-evidence-20261120/proto-tree-2x.png)

同位置放大：

![V2 原型结构树主链：skill 显示名称，subagent 显示描述](https://github.com/Shadow-Azure/harness-evolution/releases/download/execution-flow-label-evidence-20261120/proto-labels-2x.png)

因此，对用户问题的直接回答是：

1. 截图中红框位置显示的是 **subagent 的任务描述**，不是 skill 名称，也不是 subagent 名称；该 Session 没有 skill 触发事件，所以主链上没有 skill 名称。
2. V2 原型在 subagent 触发节点上同样显示任务描述，只有 skill 触发节点显示 skill 名称。生产与 V2 原型的字段选择一致，**不是生产回归**。
3. 但标签口径不一致：skill 节点用稳定名称，subagent 节点用自由文本描述；描述在 22 字处被截断（`clipName`），因此主链无法稳定看出是哪个 subagent 触发的，只能到下方子 agent 卡片找名称。

2026-11-20 提出人确认：原型与生产的 subagent 节点都改为显示 subagent 名称；skill 节点保持 skill 名称不变。实现见本 issue 的 PR（Before/After 见 PR 描述）。

## 目标

- 结构树主链的 skill 触发节点显示 skill 名称；subagent/workflow 触发节点显示 subagent 名称（`event.name`，回退 `agentType`/`kind`），任务描述放到悬浮提示（`title`），或按 `name · desc` 的紧凑格式展示。
- V2 原型与生产实现使用同一口径；原型样例数据补上 subagent 的 `name`，不再用 `desc` 充当节点标签。
- 不改变事件解析、触发坐标、排序、`×N` gap 口径、lane DAG 与子 agent 卡片布局。

## 设计依据

- [03 §8.3 Agent 执行流图：lane DAG + 结构树双视图](../../../plans/fullstack-design/03-frontend-architecture.md)：结构树继续使用 `tree/layout.ts` 的 `chainOf`，视觉基线是 V2 原型。
- V2 原型 `plans/ui-prototype-v2/harness-evolution.html`：节点链注释（“skill / subagent 触发各是一个节点”）与 `chainOf` 的“skill → name / 其他 → desc”分支；原型样例 `TREE` 里 subagent 事件只有 `desc`，子 agent 卡片显示 `type · desc · L`。
- 生产实现 `apps/web/src/components/agent-tree/tree/layout.ts` 的 `chainOf`：`event.kind === "skill" ? event.name : event.desc || event.name`。
- 服务端标签口径 `apps/api/app/service/sessions/service.py` 的 `_label`：subagent 的稳定标签取 `agent.name`，`desc` 是任务描述；树 API 同时返回两者。
- 前序 [#276](https://github.com/Shadow-Azure/harness-evolution/issues/276)：执行流 lane DAG 与结构树切换。

## 实现内容

已按“skill 名称 + subagent 名称、描述进 tooltip”的口径实现；`chainOf` 的标签取 `event.name`，悬浮 `title` 保留 `desc`；V2 原型同步从子节点类型补出名称。

- `apps/web/src/components/agent-tree/tree/layout.ts` `chainOf`：
  - skill：保持 `event.name || "skill"`。
  - agent/workflow：改为 `event.name || event.agentType || event.desc || event.kind`；`clipName` 仍只对最终文本做截断。
  - 节点 `title` 同时带 `L{line}`、name 与 desc，保证悬浮仍能读到任务描述。
- `apps/web/src/components/agent-tree/tree/nodes/AgentNode.vue`：只消费 chain item 的 `name`/`title`，不改布局；名称长度变化时确认 pill 宽度仍由 `measure` 自适应。
- V2 原型 `plans/ui-prototype-v2/harness-evolution.html`：
  - 给 `TREE` 的 agent 事件补 `name`（按样例的子 agent 类型或名称，如 `general-purpose`/`Explore`），`chainOf` 与生产改成同一规则。
  - 保留子 agent 卡片 `type · desc · L` 的信息，不删描述。
- 测试：
  - `apps/web/src/components/agent-tree/tree/layout.test.ts` 新增用例：agent 事件 `name: "code-generator"`、`desc: "Implement sliced WCS world_to_pixel fix"`，断言 chain item 文本是 `code-generator`、`title` 含 desc；skill 事件继续断言显示 skill 名称。
  - `apps/web/src/components/agent-tree/tree/AgentTree.test.ts` 或 e2e 断言渲染出的 `.rf-cnode` 文本不是长描述。
  - 如原型有快照/视觉校验，更新对应截图或断言。
- 文档：如标签口径需要长期约定，在 `plans/fullstack-design/03-frontend-architecture.md` §8.3 补一句“触发节点显示 name，desc 只做悬浮辅助”。

## 实施步骤

1. 确认统一口径：skill 名称 + subagent 名称；描述作为 tooltip。
2. 改 `chainOf` 与 `title`，补单测。
3. 更新 V2 原型 `TREE` 数据与 `chainOf`，用同一 Session 类型（含 skill 与 subagent）截图对照。
4. 跑聚焦单测、类型检查、lint、聚焦 e2e 与 `pnpm verify:flow`。
5. 在 PR 里附 Before/After：同一 Session `90e6c9f9-…` 的结构树主链，Before 是任务描述截断，After 是 `code-generator`/`spec-reviewer` 等名称；V2 原型同位置也给 Before/After。

## 依赖与交付边界

- 依赖：无；与 lane DAG 无关。
- 交付边界：只改结构树主链的触发标签、V2 原型样例与对应测试；不改 API/树契约、事件解析、`×N` 口径、lane DAG、子 agent 卡片的信息层级。
- 不把生产 Session 内容或截图提交进仓库；Before/After 截图放 PR/Release 证据。
- 若产品确认保留“描述优先”，关闭本 issue 并记录该口径，不实施本改动。

## 独立验证

```sh
pnpm --filter @harness/web exec vitest run src/components/agent-tree/tree/layout.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- "execution-flow-trigger-names"
pnpm verify:flow
```

- 用生产同构数据打开 `90e6c9f9-6f2e-4f7b-b313-a616993975e5` 的结构树：主链 6 个 subagent 节点显示 `code-generator`、`spec-reviewer`、`code-quality-reviewer`，不再是 `Implement sliced WCS …` 等描述；悬浮 `title` 仍包含原描述。
- 含 skill 的 Session（V2 原型样例 `050b81ba-…`）主链仍显示 `deep-research`、`superpowers:dispatching-parallel-agents` 等 skill 名称。
- V2 原型同位置显示同样的名称口径；子 agent 卡片仍能看到 `type · desc · L`。
- 单测、类型检查、lint、聚焦 e2e 与 `pnpm verify:flow` 全绿。

## 验收标准

- 结构树主链的 skill 触发节点显示 skill 名称；subagent/workflow 触发节点显示 subagent 名称；描述不再占用主链标签，但可在 `title` 中读到。
- 生产页面与 V2 原型使用同一规则，截图对比可复核；不出现新的截断或 pill 重叠。
- 回归测试覆盖 name/desc 不同的情况，避免以后又把 desc 放回主标签。
- 以实现 PR 的 Before/After 截图、V2 原型 After 截图与回归测试作为验收证据。

## 门禁与 CI

- `pnpm verify:flow`（本 issue 登记）
- `pnpm --filter @harness/web exec vitest run src/components/agent-tree/tree/layout.test.ts`
- `pnpm typecheck:web`、`pnpm lint:web`
- 聚焦 `pnpm test:e2e -- "execution-flow-trigger-names"`
- PR 需要 Before/After 截图与 V2 原型对照（UI 变更）

## 非目标

- 不改事件解析、触发坐标、排序、`×N` 口径和 lane DAG。
- 不改子 agent 卡片的 `type · desc · L` 信息层级。
- 不引入新的图标/图例/颜色，不做执行流整体重排。
- 不把生产数据、截图或凭据写进仓库。
