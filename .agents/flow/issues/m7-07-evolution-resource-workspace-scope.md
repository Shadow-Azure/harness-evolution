# Target、Run、Event 与 SSE 空间化

[English](m7-07-evolution-resource-workspace-scope.en.md) | 中文

```yaml flow
kind: issue
id: m7-07
milestone: m7
depends:
  - m7-03
  - m7-05
priority: P0
status: in-progress
scope:
  - apps/api/app/api/evolution_*.py
  - apps/api/app/api/events.py
  - apps/api/app/service/evolution/**
  - apps/api/app/service/events.py
  - apps/api/app/db/crud/**
  - apps/api/app/db/models/**
  - apps/api/app/api/catalogs.py
  - apps/api/app/api/deps.py
  - apps/api/app/main.py
  - apps/api/app/service/catalogs.py
  - apps/api/app/service/identity/schemas.py
  - apps/api/app/service/workspaces/service.py
  - apps/api/tests/**
  - packages/contracts/**
  - plans/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 228
  url: https://github.com/Shadow-Azure/harness-evolution/issues/228
```

## 背景

对象配置与运行历史属于空间资源；SSE 票据也必须绑定空间，避免跨空间事件泄漏。

## 目标

- evolution_targets、runs 和 events 全部按 workspace 隔离。
- 空间管理员可配置对象并启动运行。
- SSE 票据校验空间成员关系。

## 设计依据

- [01 §4.3、§4.4](../../../plans/fullstack-design/01-architecture.md)：运行与鉴权链路。
- [05 §4.20](../../../plans/fullstack-design/05-api-design.md)：V2 运行端点。

## 实现内容

- target 唯一键改为 (workspace_id, object_type, object_name)。
- run 列表、详情、重试和事件按空间过滤。
- events/ticket 绑定 workspaceId。
- 装配 V2 路由、票据字段、空间清单与可见空间过滤，同时扩展装配层（`main`、`deps`）、清单、身份契约与空间服务的 scope；这些改动只服务于本 issue 的空间边界，不改变它们的既有职责。
- 按 `docs/review.md` 产出本 PR 的结构化检视文档，落在 `plans/`。

## 实施步骤

1. 先写跨空间 target/run/SSE 测试。
2. 迁移现有服务和路由。
3. 更新兼容端点与契约。

## 依赖与交付边界

- 依赖：m7-03、m7-05
- 交付边界：不重排七步状态机。

## 独立验证

```sh
pnpm test:api -- tests/evolution tests/events; pnpm contract:check
```

- 跨空间 target/run/event 访问失败。
- 同对象名可在不同空间独立配置。
- 错误空间票据被拒绝。

## 验收标准

- 空间管理员拥有本空间操作权。
- 成员和只读成员无法写。

## 门禁与 CI

- API、事件、契约与 flow 门禁。

## 非目标

- 不实现 PotentialMatcher。
- 不改迭代/评测状态机。
