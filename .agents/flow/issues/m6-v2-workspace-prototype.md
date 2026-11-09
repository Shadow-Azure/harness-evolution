# V2 多工作空间与归因流前端原型

[English](m6-v2-workspace-prototype.en.md) | 中文

```yaml flow
kind: issue
id: m6-24
milestone: m6
depends: []
priority: P1
status: in-progress
scope:
  - plans/v2-ui-prototype/**
  - .agents/notes/**
  - .agents/flow/**
adr: []
github:
  number: 203
  url: https://github.com/Shadow-Azure/harness-evolution/issues/203
```

## 背景

现有前端已经具备登录、Session 浏览、错误详情、单一归因展示和自进化启动向导，但领域数据没有工作空间上下文，归因在启动流程之前完成，无法表达一个 bad case 对多个进化对象版本的潜在关系。V2 需要先通过可点击原型确认信息架构、权限入口、上报配置、总览下钻和多归因交互，并明确旧路由与页面的迁移方式。

## 目标

- 交付覆盖全局管理员、空间管理员、普通成员和只读成员边界的 V2 可点击前端原型。
- 覆盖工作空间与额度管理、上报接入、总览统计与分页下钻、最新 10 个 Session 与精确搜索、多归因错误详情、自进化潜在 bad case 筛选和缓存选择。
- 给出复用现有 Vue 页面、认证状态和深链的迁移方案。

## 设计依据

- [02-features.md §2.1](../../../plans/fullstack-design/02-features.md)：保留 Session 列表、执行流、bad case 与错误详情的核心页面职责。
- [02-features.md §2.2](../../../plans/fullstack-design/02-features.md)：保留进化对象、版本和时间窗作为启动条件，将命中预览扩展为关联 Session 与潜在 bad case 预览。
- [03-frontend-architecture.md §4](../../../plans/fullstack-design/03-frontend-architecture.md)：沿用路由页面、共享组件、composable 与 API 的单向依赖。
- [V2 原型设计](../../../plans/v2-ui-prototype/design.md)：在上述边界内定义工作空间上下文、多归因和迁移方案。

## 实现内容

- 新增独立静态 HTML 原型，不改生产 Vue 页面与 API。
- 新增设计说明、页面状态、权限矩阵、路由兼容与数据契约迁移建议。
- 新增 Agent Note 记录工作空间作为上层上下文和归因后移到自进化流程的决策。

## 实施步骤

1. 盘点现有原型、Vue 页面、认证边界与 bad case/自进化数据关系。
2. 编写 V2 信息架构和迁移设计，制作可点击静态原型。
3. 在浏览器检查关键交互、桌面与窄屏布局，并运行流程和文档门禁。

## 依赖与交付边界

- 依赖：现有亮色视觉令牌、登录鉴权、Session 错误详情和自进化启动向导。
- 非目标：不实现生产 API、数据库迁移、真实 Cookie 鉴权变更或前端业务逻辑。

## 独立验证

```sh
node plans/v2-ui-prototype/verify.mjs
```

- 输出全部原型结构与关键交互断言通过。

```sh
pnpm verify:flow; pnpm lint:docs
```

- 流程、双语配对、Agent Note 与文档门禁全绿。

## 验收标准

- 原型可从总览筛选并分页查询 bad case，点击后进入对应 Session 错误详情的问题描述。
- Session 默认展示 10 条，回车精确查询；错误详情中的每个 bad case 可展开多条归因并分页。
- 启动向导包含对象/版本/时间窗、Session 关联、触发点与潜在 bad case 策略、自定义策略和缓存开关。
- 工作空间创建、额度调整、成员角色与上报接入有明确入口，无公开注册入口。
- 设计文档列明旧路由兼容、现有组件复用和分阶段迁移边界。

## 门禁与 CI

- `node plans/v2-ui-prototype/verify.mjs`：静态结构断言。
- `pnpm verify:flow`：issue 三件套、scope 与状态机。
- `pnpm lint:docs`：新增 Agent Note 和流程文档的双语、链接及格式。

## 非目标

- 不在本 issue 中修改 `apps/`、`packages/contracts` 或生产测试。
- 不实现真实上报、权限校验、统计查询和归因缓存算法。
