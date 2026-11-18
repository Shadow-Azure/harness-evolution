# 工作空间总览补齐 V2 工作流入口与运营上下文

[English](m12-08-overview-v2-actions-context.en.md) | 中文

```yaml flow
kind: issue
id: m12-08
milestone: m12
depends:
  - m7-09
  - m8-04
priority: P1
status: ready
scope:
  - apps/web/src/pages/overview/**
  - apps/web/src/pages/evolution/**
  - tests/e2e/m8-04-overview.test.mjs
  - tests/e2e/m12-08-overview-actions-context.test.mjs
  - plans/**
  - docs/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 335
  url: https://github.com/Shadow-Azure/harness-evolution/issues/335
```

## 背景

2026-11-17 的生产环境与 `plans/ui-prototype-v2/harness-evolution.html` 对照显示，两者的总览骨架已经一致，但生产页首屏缺少 V2 定义的两个工作流入口，也缺少把空间额度、上报接入和当前空间放在趋势旁边的运营上下文。

生产环境总览页头只显示「只读视图 · 筛选条件保存在地址栏」，趋势图占满内容宽度；原型页头并列显示「上报接入」和「启动自进化」，趋势与运营上下文组成双栏，并提供「按 bad case 上报来源 × 时间查看问题类型明细」的可展开入口。

截图证据显示生产当前为 9 个 bad case、1 个来源、9 个关联 Session；原型为 26 个 bad case、7 个来源、11 个关联 Session。数据量差异不是本 issue 要修复的问题，本 issue 只收敛与数据无关的动作入口、权限门控和页面结构。

## 目标

- 在 bad case 总览页头提供「上报接入」和「启动自进化」入口，并按当前空间角色隐藏无权限动作。
- 入口必须复用既有空间管理页和启动向导，不引入第二个写入路径或新状态机。
- 在总览主体补回空间额度、上报地址和当前空间摘要，并保留小屏纵向堆叠。
- 将「来源 × 时间」明细入口归还到总览分析区，并保持现有 URL 筛选状态可解释。
- 为入口、空数据、无权限和响应式布局增加组件与 E2E 回归。

## 证据截图

| 生产环境 | V2 原型 |
| --- | --- |
| [![生产总览](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-01-overview-cases.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-01-overview-cases.jpeg) | [![V2 原型总览](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-01-overview-cases.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-01-overview-cases.jpeg) |

两图均为 `2816×1576` 的真实浏览器窗口截图。生产页头只有只读标签且趋势占满宽度；原型页头有两个工作流动作，趋势右侧有运营上下文。

## 设计依据

- [08 §6 工作空间总览](../../../plans/fullstack-design/08-frontend-implementation.md#6-工作空间总览页pagesoverviewindexvuev2)：总览页的数据、图表、筛选与三态结构。
- [08 §4.2 顶栏用户区、空间切换器与空间管理页](../../../plans/fullstack-design/08-frontend-implementation.md#42-顶栏用户区空间切换器与空间管理页v2)：空间角色与入口权限。
- [08 §8 自进化列表页](../../../plans/fullstack-design/08-frontend-implementation.md#8-自进化列表页pagesevolutionindexvue)：启动入口复用现有列表与向导。
- [05 §4.16 工作空间、成员与凭据](../../../plans/fullstack-design/05-api-design.md#416-工作空间成员与凭据v2)：空间额度与凭据读取边界。
- [V2 设计 §5 工作空间总览](../../../plans/ui-prototype-v2/design-v2.md#5-工作空间总览)：原型对动作区、指标、侧栏和下钻的约定。

## 实现内容

- `apps/web/src/pages/overview/Index.vue` 的页头增加「上报接入」与「启动自进化」；前者跳到当前空间的 `admin?tab=ingest`，后者打开既有 `LaunchWizard`。
- 入口依据 `canManageWorkspace(currentRole)` 和写权限矩阵决定显示或禁用，并在无权限时不渲染可绕过的空链接。
- 总览主体增加运营上下文区域，展示摘要接口已有的额度、来源数和当前空间信息；上报地址使用当前空间 ID 从既有管理接口生成，不在前端复制凭据规则。
- 来源分布卡增加「来源 × 时间」明细开关，展开后复用现有总览查询结果，不触发新的不受控写入或额外全量扫描。
- 保留当前全局筛选条；列表级筛选由 m12-09 独立处理，避免本 issue 重复实现或有冲突的 URL 状态。
- 样式复用现有 `statstrip`、`card`、`chip` 与响应式断点；窄屏时上下文区域排在趋势和列表之后。
- 单元测试覆盖管理员、空间管理员、成员/只读三种权限分支，E2E 覆盖两个入口的实际跳转和返回。

## 实施步骤

1. 先补页头入口、权限分支和空数据快照测试。
2. 把启动向导入口提升为总览级动作并复用 `useWorkspaceId`、角色判断与现有路由。
3. 增加运营上下文区域，复用已有 workspace/overview summary 查询，避免重复请求。
4. 恢复来源 × 时间明细入口，并验证展开、折叠和空态。
5. 调整 1440px、1024px 与窄屏布局，补 E2E 跳转断言。
6. 更新架构/前端文档并补 Agent Note，运行聚焦测试和全量门禁。

## 依赖与交付边界

- 依赖：m7-09 提供空间管理页，m8-04 提供总览主体；两者均已完成。
- 交付边界：只补总览页入口与运营上下文；不改变额度、凭据、成员或自进化运行语义。
- 不新增数据库字段、不新增 API；若现有响应不足以渲染上下文，优先复用现有 workspaces/overview 端点，并把必要的窄字段补丁拆成明确子任务。
- 列表级日期/来源/类型筛选由 m12-09 交付，触发点列由 m12-10 交付，避免同一 PR 扩大为跨栈重构。

## 独立验证

```sh
pnpm test:web -- apps/web/src/pages/overview/Index.test.ts
pnpm test:e2e -- --pattern m12-08
pnpm typecheck:web
pnpm verify:bundle
```

- 总览管理员视图同时看到「上报接入」「启动自进化」和运营上下文。
- 入口分别到达当前空间的 `admin?tab=ingest` 与启动向导；返回后筛选条件保持。
- 无管理权限用户看不到写入口；成员仍可读总览。
- E2E 在 1440px 和窄屏下无横向溢出。
- `verify:bundle` 不把新入口带入无关首屏 chunk。

## 验收标准

- bad case 总览首屏具备 V2 约定的两个工作流入口，并遵守空间角色权限。
- 空间额度、上报地址和当前空间摘要在桌面为右侧上下文，在窄屏为主内容之后的纵向卡片。
- 来源 × 时间明细可展开且与当前筛选一致；空态不显示伪造数据。
- 入口跳转全部复用现有页面与路由，返回路径不丢失 URL 中的筛选状态。
- 新测试和文档通过 CI，既有总览统计、趋势、列表与分页不回归。

## 门禁与 CI

- `pnpm test:web`、`pnpm test:e2e`、`pnpm typecheck:web`、`pnpm verify:bundle`、`pnpm lint:docs`、`pnpm verify:flow`。
- PR 必须附生产/原型对照截图或 DOM 断言；涉及角色分支时至少覆盖管理员和只读成员。

## 非目标

- 不修改工作空间额度、成员或凭据的服务端规则。
- 不把原型演示的 26 个 bad case 或固定空间名称写入生产 fixtures。
- 不在本 issue 实现列表级筛选或触发点列。
- 不恢复已裁撤的时间线页面。
