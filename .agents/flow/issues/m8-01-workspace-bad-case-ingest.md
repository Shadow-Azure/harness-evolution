# 空间 bad case 上报、额度与幂等

[English](m8-01-workspace-bad-case-ingest.en.md) | 中文

```yaml flow
kind: issue
id: m8-01
milestone: m8
depends:
  - m7-05
  - m7-06
priority: P0
status: done
scope:
  - apps/api/app/api/ingest.py
  - apps/api/app/service/workspaces/**
  - apps/api/app/db/crud/**
  - apps/api/app/middleware/**
  - apps/api/app/errors.py
  - apps/api/app/main.py
  - apps/api/tests/**
  - apps/web/src/pages/workspaces/**
  - packages/contracts/**
  - plans/**
  - docs/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 231
  url: https://github.com/Shadow-Azure/harness-evolution/issues/231
```

## 背景

每个空间需要稳定的机器上报入口，并以事务保证额度、幂等和跨空间冲突边界。

## 目标

- 实现 Bearer 空间凭据上报。
- 重复 badCaseId 更新但不重复占额度。
- 额度耗尽返回 409 且不删除旧数据。

## 设计依据

- [05 §3.8、§4.17](../../../plans/fullstack-design/05-api-design.md)：上报 DTO 与端点。
- [06 §4.1](../../../plans/fullstack-design/06-database-design.md)：bad_cases 归属与索引。

## 实现内容

- body 不接受 workspaceId。
- 事务内锁定空间行并统计 used。
- 成功后标记 root session 待补轨迹。

## 实施步骤

1. 先写并发额度与幂等测试。
2. 实现凭据认证、写入与 root sync 标记。
3. 增加 curl 契约和 OpenAPI。

## 依赖与交付边界

- 依赖：m7-05、m7-06
- 交付边界：不实现上报接入前端。

## 独立验证

```sh
pnpm test:api -- tests/ingest; pnpm test:db; pnpm test:db:mysql
```

- 第 quota 条成功、下一条 409。
- 同 ID 重报不增加 used。
- 跨空间 ID 返回 409。

## 验收标准

- 凭据只可调用上报端点。
- 事务并发不超卖。

## 门禁与 CI

- API、双方言数据库、契约与 flow 门禁。

## 非目标

- 不开放注册。
- 不允许 body 指定空间。
