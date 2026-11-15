# 空间权限依赖与 auth/session 聚合

[English](m7-03-workspace-rbac-auth-session.en.md) | 中文

```yaml flow
kind: issue
id: m7-03
milestone: m7
depends:
  - m7-02
priority: P0
status: done
scope:
  - apps/api/app/api/**
  - apps/api/app/db/crud/workspaces.py
  - apps/api/app/service/workspaces/**
  - apps/api/app/service/identity/**
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
  number: 224
  url: https://github.com/Shadow-Azure/harness-evolution/issues/224
```

## 背景

只有登录身份还不够；每个业务请求都要在服务端判断用户对目标空间的可见性和最低角色。

## 目标

- 提供 require_workspace_role 权限依赖。
- 让 auth/session 一次返回 user 与可见 workspaces。
- 不可见空间统一返回 404。

## 设计依据

- [01 §4.4](../../../plans/fullstack-design/01-architecture.md)：鉴权与空间授权链路。
- [07 §5.15、§8.2.1](../../../plans/fullstack-design/07-backend-implementation.md)：权限依赖与会话聚合。

## 实现内容

- 实现 viewer < member < space_admin 等级比较。
- 全局管理员直通但可写入真实空间成员行。
- auth/session 使用批量查询返回 used、memberCount 和有效角色。
- 仓储按设计落在 `app/db/crud/workspaces.py`；装配点（`main.py`、`errors.py`、`middleware/auth.py`）、`apps/api/tests` 与 `plans/` 检视记录一并纳入 scope。

## 实施步骤

1. 先写权限矩阵与会话截断测试。
2. 实现 WorkspaceRepository 和权限依赖。
3. 注册 auth/session 并更新契约。

## 依赖与交付边界

- 依赖：m7-02
- 交付边界：不实现成员写操作和前端空间壳。

## 独立验证

```sh
pnpm test:api -- tests/workspaces tests/identity; pnpm contract:check
```

- 四种身份 × 各最低角色逐格通过。
- 不可见空间返回 404。
- auth/session 不超过 200 个空间并正确标记截断。

## 验收标准

- 后续业务端点可以统一复用权限依赖。
- 普通用户只看到所属空间。
- 全局管理员看到全部空间。

## 门禁与 CI

- API、契约与 flow 门禁。

## 非目标

- 不在 JWT 中固化空间角色。
- 不开放注册。
