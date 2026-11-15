# V2 契约与空间基座迁移

[English](m7-02-v2-contracts-workspace-foundation.en.md) | 中文

```yaml flow
kind: issue
id: m7-02
milestone: m7
depends: []
priority: P0
status: backlog
scope:
  - apps/api/app/db/**
  - apps/api/alembic/**
  - packages/contracts/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 223
  url: https://github.com/Shadow-Azure/harness-evolution/issues/223
```

## 背景

空间权限、bad case 归属和后续归因都依赖同一组共享契约与可重复迁移。

## 目标

- 加入 Workspace、Member、Credential 和 SessionPayload 契约。
- 创建空间三表并为业务表增加 workspace_id。
- 支持默认空间幂等回填和双方言迁移。

## 设计依据

- [05 §3.7、§4.16](../../../plans/fullstack-design/05-api-design.md)：空间 DTO 与端点。
- [06 §3.10–§3.12、§9](../../../plans/fullstack-design/06-database-design.md)：空间表与迁移。

## 实现内容

- 扩展 users 的 auth_provider 与 external_subject。
- 新增 workspaces、workspace_members、workspace_ingest_credentials。
- 为 bad_cases、evolution_targets、evolution_runs、evolution_run_events 增加 workspace_id 与索引。

## 实施步骤

1. 先写 SQLite 与 MySQL 迁移失败测试。
2. 实现模型和第一组 Alembic 迁移。
3. 生成 OpenAPI 与 TS 类型并更新快照。

## 依赖与交付边界

- 依赖：无
- 交付边界：只建立基座，不开放业务端点。

## 独立验证

```sh
pnpm test:db; pnpm test:db:mysql; pnpm contract:check
```

- 空库升级和重复升级通过。
- 默认空间回填后无 NULL workspace_id。
- OpenAPI 生成物无漂移。

## 验收标准

- 两方言均可建立空间基座。
- 存量数据全部归入默认空间。
- 跨空间唯一键约束生效。

## 门禁与 CI

- 双方言迁移、契约与 flow 门禁。

## 非目标

- 不实现鉴权会话聚合。
- 不迁移多归因表。
