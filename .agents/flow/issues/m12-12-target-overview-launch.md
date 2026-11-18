# 进化对象总览提供直接启动入口

[English](m12-12-target-overview-launch.en.md) | 中文

```yaml flow
kind: issue
id: m12-12
milestone: m12
depends:
  - m11-04
  - m12-06
  - m12-08
priority: P2
status: done
scope:
  - apps/web/src/pages/overview/**
  - tests/e2e/m11-04-target-overview.test.mjs
  - tests/e2e/m12-12-target-overview-launch.test.mjs
  - plans/**
  - docs/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 339
  url: https://github.com/Shadow-Azure/harness-evolution/issues/339
```

## 背景

生产「进化对象总览」页头只显示「+ 新增进化对象」和只读标签；V2 原型在同一页头同时提供「+ 新增进化对象」和「启动自进化」。

对象总览本身就是用户查看对象、潜在 bad case 和归因状态的页面。缺少启动入口迫使管理员先返回自进化列表再打开向导，打断从对象分布到运行的路径。

该差异与当前空间是否有对象无关：现有时序守卫已经能在没有启用对象时给出配置提示，入口仍应保持可见并由统一权限与向导逻辑处理空配置。

## 目标

- 在「进化对象总览」页头增加「启动自进化」，与「+ 新增进化对象」并列。
- 入口复用 m12-08 提供的共享启动动作和既有 `LaunchWizard`，不复制四步表单。
- 仅管理角色可见；无权限角色保持只读总览。
- 无启用对象时允许入口打开既有配置提示，不在前端重复判断目标是否可用。
- 补组件/E2E 覆盖从对象总览启动、关闭和配置跳转。

## 证据截图

| 生产环境 | V2 原型 |
| --- | --- |
| [![生产进化对象总览](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-02-overview-targets.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-02-overview-targets.jpeg) | [![V2 原型进化对象总览](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-02-overview-targets.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-02-overview-targets.jpeg) |

两图均为 `2816×1576` 的真实浏览器窗口截图。生产页头只有「+ 新增进化对象」；原型页头同时显示「+ 新增进化对象」和「启动自进化」。生产空态来自当前空间没有启用对象，不作为动作缺失的依据。

## 设计依据

- [08 §6 工作空间总览](../../../plans/fullstack-design/08-frontend-implementation.md#6-工作空间总览页pagesoverviewindexvuev2)：对象总览与列表入口。
- [08 §8 自进化列表页](../../../plans/fullstack-design/08-frontend-implementation.md#8-自进化列表页pagesevolutionindexvue)：既有启动入口和向导归属。
- [08 §9.1 启动向导状态机](../../../plans/fullstack-design/08-frontend-implementation.md#91-状态机)：无对象守卫和四步流程。
- [V2 设计 §5.3 双视角](../../../plans/ui-prototype-v2/design-v2.md#53-双视角bad-case--进化对象)：对象总览的共享上下文与动作。
- [V2 设计 §7 归因进入自进化](../../../plans/ui-prototype-v2/design-v2.md#7-归因进入自进化)：从对象上下文启动进化的流程。

## 实现内容

- 在 `TargetsOverview` 的页头动作区增加「启动自进化」按钮，位置与 bad case 总览共享页头一致。
- 使用 m12-08 导出的共享启动回调或小型 composable；若 m12-08 采用 query 激活，则沿用同一实现。
- 权限与 `+ 新增进化对象` 使用同一 `canManage` 条件；不新增第二套角色判断。
- 空对象时按钮仍可触发既有 `LaunchWizard` 空配置守卫，跳转 `/evolution/targets` 后原空间上下文不丢失。
- 测试覆盖管理员、空间管理员、成员/只读、无对象、有关闭向导和返回路径。

## 实施步骤

1. 先补对象总览页头动作和权限分支失败测试。
2. 接入 m12-08 的共享启动动作，确认不导入重复向导状态。
3. 验证无启用对象时进入配置守卫且配置链接保持当前空间。
4. 补 E2E 从对象总览启动、关闭、返回和配置跳转。
5. 更新对象总览文档/测试说明，运行 web、E2E、类型和流程门禁。

## 依赖与交付边界

- 依赖：m11-04 提供对象总览，m12-06 提供配置错误体验，m12-08 提供总览共享启动入口；前三者均须已完成。
- 交付边界：只增加对象总览的入口接线，不修改启动向导步骤、运行创建或目标匹配。
- 入口处理无对象守卫，但不在前端预先禁用；服务端和现有向导继续作为真实权限/配置边界。
- 不在本 issue 新增对象配置弹窗或自进化路由。

## 独立验证

```sh
pnpm test:web -- apps/web/src/pages/overview/components/TargetsOverview.test.ts
pnpm test:e2e -- --pattern m12-12
pnpm typecheck:web
pnpm verify:flow
```

- 管理角色在对象总览看到「启动自进化」，只读角色看不到。
- 点击后打开既有启动向导；无对象时显示配置守卫。
- 关闭或返回后仍停留在对象总览，筛选与时间范围不丢失。
- 配置跳转使用当前 `workspaceId`，不回到默认空间。

## 验收标准

- 对象总览页头同时存在新增对象与启动自进化动作，且布局不挤压窄屏标题。
- 启动动作复用 m12-08/现有向导，不产生第二份步骤状态。
- 权限、空配置、关闭和配置跳转均有自动化覆盖。
- 现有对象统计、趋势、筛选、分页和单对象分析不回归。
- 新测试与文档通过 CI。

## 门禁与 CI

- `pnpm test:web`、`pnpm test:e2e`、`pnpm typecheck:web`、`pnpm verify:bundle`、`pnpm lint:docs`、`pnpm verify:flow`。
- PR 附对象总览页头截图；无权限场景用 DOM 断言证明按钮不存在。

## 非目标

- 不修改启动向导四步定义或运行 API。
- 不在对象总览内直接执行目标匹配或归因。
- 不增加新的对象配置入口或改变配置错误语义。
- 不把无对象用户锁死在对象总览；仍提供既有配置引导。
