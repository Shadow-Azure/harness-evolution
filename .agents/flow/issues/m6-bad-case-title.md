# bad_cases 增加短标题 title

[English](m6-bad-case-title.en.md) | 中文

```yaml flow
kind: issue
id: m6-12
milestone: m6
depends: []
priority: P1
status: backlog
scope:
  - packages/contracts/**
  - apps/api/**
  - apps/web/**
  - fixtures/**
  - reports/**
  - plans/fullstack-design/**
  - .agents/flow/**
  - .agents/notes/**
adr:
  - ../../notes/proposed/feature/2026-10-29-bad-case-title.md
github:
  number: 165
  url: https://github.com/Shadow-Azure/harness-evolution/issues/165
```

## 背景

原型错误详情页按两级文本渲染问题：短标题 + 描述正文，问题列表卡与 Agent 执行流图问题卡同样以短标题为主文本。当前数据模型只有 `bad_cases.reason` 一个长文本字段，错误详情页把 `reason` 直接当标题渲染，没有正文层级；问题列表卡在未分析时只能显示"尚未完成归因分析"，没有可读的题名。契约 `BadCase` / `SessionBadCase` 与 `bad_cases` 表都只有 `reason`，[05 §9](../../../plans/fullstack-design/05-api-design.md) 的原型字段映射表没有把原型 `finding.title` / `finding.detail` 映射到任何接口字段——短标题在设计映射时缺失，这是数据模型缺口，不是前端实现偏差。真实数据接入后（灌入 `trajectory_payloads` 并上报 `bad_cases`）该缺口在错误详情页直接可见。

## 目标

- `bad_cases` 增加 `title` 短标题列（外部上报必填），`reason` 语义收敛为"描述正文"。
- 契约 `BadCase` / `SessionBadCase` 增加 `title`，OpenAPI 与生成类型跟随再生。
- 错误详情页标题行渲染 `title`、正文块渲染 `reason`；问题列表卡与执行流图问题卡以 `title` 为主文本。
- 上游问题上报契约把 `title` 列入必填字段，fixtures 演示数据同步补齐。

## 设计依据

- [06 数据库设计 §4.1](../../../plans/fullstack-design/06-database-design.md)：`bad_cases` 列定义，`title` 列与本节同步修订。
- [05 接口设计 §3.4](../../../plans/fullstack-design/05-api-design.md)：`BadCase` DTO 与字段语义，增加 `title`。
- [05 接口设计 §9](../../../plans/fullstack-design/05-api-design.md)：原型字段映射对照表，补 `title` / `reason` 两级文本的映射行。
- [原型 harness-evolution.html](../../../plans/14-15-ui-prototype/harness-evolution.html)：`FindingDescription` 的 title + detail 两级文本是渲染基准。
- 实现冲突时以上链接章节和已确认原型为准。

## 实现内容

- `bad_cases` 增加 `title VARCHAR(255) NOT NULL`：`apps/api/app/db/models/domain.py` 同步列，alembic 新增迁移；存量行按 [06 §1.2](../../../plans/fullstack-design/06-database-design.md) 由上游重灌，或一次性回填（取 `reason` 首句截断）。
- `packages/contracts` 的 BadCase / SessionBadCase schema 增加 `title`，`pnpm contract:generate` 再生 `openapi.json` 与生成类型。
- API 装配层透出 `title`：repository 读取、service 读模型、路由响应；字段缺失的降级展示沿用现有 `degraded` 机制。
- Web：错误详情页标题行渲染 `title` 并新增正文块渲染 `reason`；问题列表卡（`BadCaseList.vue`）与执行流图问题卡（`BadCaseNode.vue`、`layout.ts` 卡宽测量）主文本改用 `title`。
- fixtures：`fixture_corpus.py` 与 `fixtures/` 演示数据的问题记录补 `title`。

## 实施步骤

1. 契约先行：contracts schema 增加 `title`，运行 `pnpm contract:generate`，前后端生成类型跟随。
2. 数据库：domain 模型加列，alembic 迁移（SQLite batch 模式），`pnpm test:db[:mysql]` 双库验证。
3. API：repository / service / 路由透出 `title`，补读模型单测与降级路径用例。
4. Web：详情页两级渲染、列表卡与图上问题卡切换 `title`，补组件测试。
5. fixtures 演示数据补 `title`，运行 `pnpm fixtures:check`。

## 依赖与交付边界

- 依赖：无
- 交付边界：`bad_cases` 数据模型、共享契约、问题读接口与问题展示；不改变归因状态机、锚点算法与 `probe_reports` 结构；问题侧仍由外部系统写入，本服务不新增上报写路径。

## 独立验证

```sh
pnpm contract:check
pnpm test:db
pnpm --filter @harness/web exec vitest run src/pages/errors src/components/bad-cases
pnpm fixtures:check
```

- `BadCase` / `SessionBadCase` 契约含 `title`，`contract:check` 绿。
- fixtures 演示会话的每条问题带非空 `title`；错误详情页标题行显示短标题、正文块显示 `reason`。

## 验收标准

- `/sessions/{sid}/errors` 问题描述 tab：标题行是 `title` 短标题，正文块是 `reason` 完整描述；未分析、非问题、是问题三种状态同样成立。
- 问题列表卡与 Agent 执行流图问题卡主文本为 `title`，图上卡片宽度钳制（150–400px）行为不变。
- DB 结构、OpenAPI、API 响应三方一致（`pnpm contract:check` 绿）。
- 上游未提供 `title` 的存量/异常数据有降级或回填路径并有测试覆盖。

## 门禁与 CI

- `pnpm contract:generate` / `pnpm contract:check`
- `pnpm typecheck:api` / `pnpm test:api` / `pnpm test:db[:mysql]`
- `pnpm test` / `pnpm typecheck:web` / `pnpm lint:web`
- `pnpm fixtures:check`
- `pnpm verify:flow` / `pnpm lint:docs` / `pnpm verify:docs`

## 非目标

- 不复验"错误卡→skill 触发点连线被 Agent 框遮挡"：#149/#152 已交付 edge 层修复，最新 main 上的复验另行立 issue。
- 不改 `probe_reports` / `bad_case_analysis` 结构与归因状态机。
- 不新增问题上报写接口；问题侧仍由外部系统写入，`title` 列的写入方是上游。
