# 进化对象表单移除启用开关，新增对象默认启用

[English](bugfix-target-enabled-switch.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-66
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - apps/web/**
  - plans/**
  - .agents/**
  - tests/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-26-target-enabled-switch.md
github:
  number: 628
  url: https://github.com/Shadow-Azure/harness-evolution/issues/628
```

## 背景

生产「进化对象配置 → 新增/编辑进化对象」表单底部的 `启用` 开关同时表达「对象总启用」和「进入启动向导候选」两层含义；`启用` 与 `启动` 两个近义词上下叠放，用户无法判断开关是在启用对象，还是只把对象加进启动向导。核对代码后确认 `enabled` 实际影响启动向导目录、启动/探测、后台归因队列与进化对象总览，表单只描述向导候选会误导用户。先尝试改写文案（字段名「参与自进化」+ 停用影响说明），但反馈仍然偏复杂。最终决定：从表单移除该选项，新增对象默认启用，停用/启用继续由配置列表的既有动作承担。

## 目标

- 从 `TargetFormDialog.vue` 移除 `启用` 表单项及 `ElSwitch`，表单在「主指标 key」后直接进入底部操作区。
- 新增对象提交 `enabled: true`；编辑停用对象保存时保留当前 `enabled`，不静默启用。
- 配置列表的「已启用/已停用」状态与「启用/停用」动作保持不变，并继续作为唯一状态切换入口。
- 不修改后端、契约、数据库字段与启动/归因/总览行为。

## 设计依据

- [08 §9.5 进化对象配置页](../../../plans/fullstack-design/08-frontend-implementation.md#95-进化对象配置页evolutiontargets)：表单字段、必填校验与保存行为。
- [V2 原型 `plans/ui-prototype-v2/harness-evolution.html`](../../../plans/ui-prototype-v2/harness-evolution.html)：移除开关后的表单形态与截图对照。
- [GitHub issue #628](https://github.com/Shadow-Azure/harness-evolution/issues/628)：歧义描述、用户决定与原型修改前后截图。

## 实现内容

- `apps/web/src/pages/evolution/targets/components/TargetFormDialog.vue`：删除 `ElFormItem label="启用"` 与 `.switch-row` 样式；保留 `form.enabled` 初始化（`props.target?.enabled ?? true`）和提交字段。
- `apps/web/src/pages/evolution/targets/components/TargetFormDialog.test.ts`：删除 `.el-switch` 断言；覆盖新增提交 `enabled: true`、编辑停用对象保持 `enabled: false`、表单不再出现 `.el-switch` 与「进入启动向导候选」。
- `plans/ui-prototype-v2/harness-evolution.html`：删除原型表单中的启用开关。
- `plans/fullstack-design/08-frontend-implementation.md` §9.5：同步表单结构说明，补充新增默认启用、编辑保留、列表切换的边界。
- `tests/e2e/m5-target-config.test.mjs`：停用对象后进入编辑，断言表单无开关且保存后仍为停用；列表切换覆盖保留。
- Agent Note：记录移除原因、被否的文案改写方案与状态仍由列表承担的决定。

## 实施步骤

1. 先改组件测试，覆盖新增默认启用与编辑停用对象保持停用。
2. 删除表单开关与 `.switch-row` 样式，保留 `form.enabled` 初始化/提交。
3. 更新设计文档与原型；跑聚焦单测、类型检查、lint、flow/docs 门禁。
4. 真实浏览器冒烟：新增对象默认「已启用」；编辑停用对象保存后仍「已停用」；列表动作可切换。

## 依赖与交付边界

- 依赖：无。
- 非目标：不改变 `enabled` 的后端语义、API 契约、数据库字段或启动/归因/总览行为；不移除列表的「停用/启用」动作；不新增第二个开关。

## 独立验证

```sh
pnpm test:web -- src/pages/evolution/targets
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- "m5 target configuration"
pnpm verify:flow
pnpm lint:docs
```

- 组件测试覆盖新增 `enabled: true`、编辑停用对象 `enabled: false`、表单无 `.el-switch` 且不含「进入启动向导候选」。
- 目标配置 E2E 覆盖「停用后编辑，表单无开关且保存后仍停用」。
- 浏览器冒烟覆盖新增、编辑停用、列表切换三条路径；截图与 V2 原型同视口对照。
- 上述命令全绿。

## 验收标准

- 新增/编辑表单不再出现 `启用`、`进入启动向导候选` 或任何替代开关。
- 新增对象创建后状态为「已启用」；编辑停用对象保存后仍为「已停用」。
- 列表的「停用/启用」动作可正常切换，状态徽标与筛选不变。
- 同一 V2 原型、同一 1500×837 CSS @2x 视口提供修改前后截图；PR 附 Before/After。

## 门禁与 CI

- `pnpm test:web`、`pnpm typecheck:web`、`pnpm lint:web`。
- `pnpm verify:flow`、`pnpm lint:docs`、`pnpm test:gates`。
- GitHub CI 全部通过后由维护者合并。

## 非目标

- 不改变 `enabled` 的后端语义、API 契约、数据库字段或启动/归因/总览行为。
- 不移除配置列表的「停用/启用」动作，也不改变列表状态文案。
- 不新增「仅隐藏向导」之类的第二个开关，也不再为表单补充替代说明文案。
- 不重排表单其它字段。
