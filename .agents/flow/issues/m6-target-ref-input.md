# 修复进化对象基线引用输入与标签加载

[English](m6-target-ref-input.en.md) | 中文

```yaml flow
kind: issue
id: m6-07
milestone: m6
depends:
  - m5-03
priority: P1
status: in-progress
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
adr:
  - ../../notes/implemented/feature/2026-10-27-target-config-ui.md
github:
  number: 153
  url: https://github.com/Shadow-Azure/harness-evolution/issues/153
```

## 背景

### 问题是什么

“新增进化对象”浮窗把 `defaultRef` 渲染为可筛选、可新建的 `ElSelect`，但输入文字只进入组件内部的过滤状态，只有按 Enter 或点击下拉中的新建项才会更新 `v-model`；用户输入后直接移开焦点或点击“新增配置”时，已输入的分支或标签会被丢弃并触发必填错误。

新增态还没有 target id，而现有版本接口 `GET /api/evolution/targets/{targetId}/versions` 只能按已保存对象查询，因此页面既不请求仓库 tag，又因为把禁用查询的 `isPending` 当作加载态而持续显示“正在读取仓库版本…”。后端实际允许分支或 tag，但版本接口只返回 tag，且新增时无法取得任何远端建议。

### 问题现象

- 打开“新增进化对象”后，基线字段表现为空下拉，并持续显示“正在读取仓库版本…”。
- 手动输入 `main`、`feature/foo` 或 `v2.0.0` 后直接点击其他字段或“新增配置”，输入值消失，表单提示“请填写基线分支或标签”。
- 只有输入后按 Enter，或点击下拉中临时出现的新建项，值才会写回表单。
- 编辑已有对象时会读取该对象已保存仓库的 tag，但当前分支仅因被额外加入 option 才可见；修改仓库地址后，建议仍来自旧仓库，直到保存并重新查询。

### 问题影响

- 管理员按普通文本输入的使用习惯无法完成新增，容易误判为字段只读或仓库不可用。
- 配置页承诺“基线分支或标签”，但新增时既不能发现 tag，也不能发现分支，形成必须先凭记忆填写才能获得建议的循环依赖。
- 现有组件测试直接向 `ElSelect` 发出 `update:modelValue`，绕过了真实输入与失焦过程，因此没有捕获该回归。

### 根因分析

- `TargetFormDialog.vue` 使用 `ElSelect` 的 `filterable + allow-create` 接收自由值，但表单 `v-model` 不会随输入文本实时更新；Element Plus 只在选择 option 时提交模型值，失焦仅关闭下拉并清空内部过滤文本。
- `Index.vue` 只在 `editingTarget` 有 id 时启用版本查询；新增态的 id 为空，无法调用只接受 target id 的后端接口。
- TanStack Query 对禁用查询仍报告 `status=pending`，页面却用 `isPending` 代替实际请求状态，导致新增态出现永久加载提示。
- 后端保存校验使用 `git ls-remote <repo> <ref>`，接受可解析的分支或 tag；版本读取使用 `git ls-remote --tags`，只列出 tag，前后端能力描述并不完全对称。

### 建议

- 将“基线分支或标签”调整为输入优先的可编辑组合框：输入文本本身就是待提交值，进入建议列表或选择 tag 只是可选增强；失焦和表单提交前都必须保留并规范化当前文本。
- 保留 Enter 和点击建议项的快捷行为，但不得要求用户用它们完成普通输入。
- 新增态不伪造远端 tag 加载；在 target 保存前允许直接填写分支或 tag，并明确提示保存后才可基于已配置仓库选择 tag。若未来需要在保存前提供 tag，应设计受控的后端查询边界，不从浏览器直接探测仓库，也不把任意 `repoUrl` 探测能力开放给普通登录用户。
- 仅在真实请求发生时显示加载态，使用实际 fetch 状态，而不是禁用查询的 pending 状态。
- 测试改为驱动真实输入、失焦和表单提交，并覆盖新增态无 target id、编辑态 tag 建议、当前分支不在 tag 列表以及 422 后保留输入。

## 目标

- 新增态可直接输入并保存任意合法的远端分支或 tag，无需隐式选择或按 Enter。
- 新增态不再显示无请求支撑的版本加载提示，编辑态仍能展示已保存仓库的 tag 建议。
- 基线字段的输入、建议、提交和错误保留语义一致，并有真实 DOM 交互测试覆盖。

## 设计依据

- [plans/fullstack-design/08-frontend-implementation.md §9.5](../../../plans/fullstack-design/08-frontend-implementation.md#95-进化对象配置页evolutiontargets)：基线字段是分支或 tag，版本建议来自仓库 tag。
- [plans/fullstack-design/05-api-design.md §4.11](../../../plans/fullstack-design/05-api-design.md#411-进化对象配置仅配置后可自进化)：新增保存接受分支或 tag，版本端点为按 target id 读取 tag。
- 实现冲突时以上链接与当前后端 `GitRemote` 校验语义为准。

## 实现内容

- 调整基线字段组件，使文本输入值成为受控表单值，远端 tag 仅作为可选建议。
- 处理失焦和表单提交前的值同步，确保直接填写后点击其他控件或提交不会丢失文本。
- 修正新增态的版本请求与加载状态，不在没有 target id 或没有真实请求时显示“正在读取”。
- 保持编辑态 tag 建议和当前 `defaultRef` 可见性，并保证分支不在 tag 列表时仍可正常保存。
- 更新对应设计说明，并新增 Agent Note 记录输入优先、建议次要与新增态远端建议边界的理由。

## 实施步骤

1. 先补失败测试：真实输入后失焦、真实输入后直接提交、新增态不发版本请求、新增态不显示加载、编辑态显示 tag 建议。
2. 调整基线字段的受控值同步，使输入文本在选择建议前也可进入表单状态。
3. 收紧版本查询加载条件，只在存在 target id 且请求真实进行时展示 loading。
4. 更新前端实现说明和 Agent Note，明确新增阶段与已保存阶段可提供的建议差异。
5. 运行聚焦单测、前端类型与 lint、流程门禁、文档门禁和配置页 E2E。

## 依赖与交付边界

- 依赖：m5-03
- 交付边界：修复配置页基线字段的输入语义、新增态版本建议加载和相应测试；不改变后端 `git ls-remote` 的分支/tag 校验规则。

## 独立验证

```sh
pnpm --filter @harness/web exec vitest run src/pages/evolution/targets/components/TargetFormDialog.test.ts src/pages/evolution/targets/Index.test.ts src/composables/useEvolutionTargets.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- "m5 target configuration"
pnpm verify:flow
pnpm verify:docs
```

- 新增用例真实输入分支后失焦或提交，断言请求体保留完整 `defaultRef`。
- 新增态版本查询不发请求，且页面不持续显示加载；编辑态 tag 建议与当前分支仍可见。
- 422 `REPO_INVALID` 后表单保持打开且输入不丢失。
- 前端类型、lint、流程、文档与配置页 E2E 全部通过。

## 验收标准

- 在“新增进化对象”中直接输入 `main`、`feature/foo` 或 `v2.0.0` 后点击其他字段，再点击“新增配置”，请求体包含规范化后的输入值。
- 用户无需按 Enter、无需点击下拉新建项即可保存合法分支或 tag。
- 新增态不再出现“正在读取仓库版本…”或无限 loading；只有真实版本请求进行时显示加载。
- 编辑已有对象时仍可从仓库 tag 中选择，当前分支不在 tag 列表中也能正常显示和保存。
- 不存在或不可达的 ref 仍由后端返回 `REPO_INVALID`，错误展示在表单内且所有输入保留。
- 组件测试覆盖真实输入与失焦路径，不再只通过程序化发出 `update:modelValue` 模拟成功。

## 门禁与 CI

- `pnpm test:web`
- `pnpm typecheck:web`
- `pnpm lint:web`
- `pnpm test:e2e -- "m5 target configuration"`
- `pnpm verify:flow`
- `pnpm lint:docs` / `pnpm verify:docs`

## 非目标

- 不改变后端对分支、tag、仓库地址或子目录的安全校验规则。
- 不为任意登录用户新增按未保存 `repoUrl` 探测远端的能力。
- 不把版本建议改成必须从远端 tag 中选择，也不改变启动向导的版本选择行为。
- 不重构整个目标配置页或运行启动链路。
