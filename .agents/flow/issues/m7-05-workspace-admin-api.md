# 空间管理、成员与上报凭据 API

[English](m7-05-workspace-admin-api.en.md) | 中文

```yaml flow
kind: issue
id: m7-05
milestone: m7
depends:
  - m7-03
  - m7-04
priority: P0
status: done
scope:
  - apps/api/app/api/workspaces.py
  - apps/api/app/service/workspaces/**
  - apps/api/app/db/crud/workspaces.py
  - apps/api/app/main.py
  - apps/api/app/errors.py
  - apps/api/app/middleware/auth.py
  - apps/api/tests/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 226
  url: https://github.com/Shadow-Azure/harness-evolution/issues/226
```

## 背景

全局管理员要创建空间并任命空间管理员；空间管理员要管理额度、成员和上报凭据。

## 目标

- 实现空间 CRUD、成员角色和自任空间管理员。
- 实现凭据创建、轮换和撤销。
- 保证空间管理员不能授予或修改 space_admin。

## 设计依据

- [05 §4.16](../../../plans/fullstack-design/05-api-design.md)：空间管理端点。
- [07 §5.15](../../../plans/fullstack-design/07-backend-implementation.md)：成员与凭据规则。

## 实现内容

- 创建空间必须至少带一个空间管理员。
- 成员候选搜索不暴露全局用户目录。
- 凭据只返回一次明文，数据库仅保存哈希。

## 实施步骤

1. 先写成员锁与凭据轮换测试。
2. 实现 service、repository 和 routes。
3. 更新 OpenAPI 与错误码。

## 依赖与交付边界

- 依赖：m7-03、m7-04
- 交付边界：不实现上报写入。

## 独立验证

```sh
pnpm test:api -- tests/workspaces; pnpm contract:check
```

- 空间管理员授 space_admin 返回 403。
- 最后一个空间管理员不可移除。
- 旧凭据撤销后认证失败。

## 验收标准

- 完整权限矩阵通过。
- 凭据明文不进入日志或数据库。

## 门禁与 CI

- API、契约、安全和 flow 门禁。

## 非目标

- 不做空间删除或归档。
- 不做成员历史表。
