# Users migration and auth backend

English | [中文](m1-06-identity-backend.md)

```yaml flow
kind: issue
id: m1-06
milestone: m1
depends:
  - m1-03
  - m1-04
priority: P0
status: in-progress
scope:
  - AGENTS.md
  - apps/api/**
  - apps/api/alembic/**
  - packages/contracts/**
  - scripts/**
  - tests/integration/**
  - .github/workflows/ci.yml
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 29
  url: https://github.com/Shadow-Azure/harness-evolution/issues/29
```

## Background





单组织 SaaS 要求真实账号与短命 access JWT；SSE 与所有业务 API 都依赖这个接缝。

## Goals





- 实现 users 迁移、argon2id、初始管理员播种、登录/刷新/登出/改密。
- 强制首登改密，保护业务 API，并对 SSE 发一次性 topic 票据。
- 契约与错误码全部通过 OpenAPI 生成。

## Design authority





- [04 后端架构](../../../plans/fullstack-design/04-backend-architecture.md)

## Implementation





- access 存内存 30 分钟，refresh 用 httpOnly/SameSite=Strict cookie 14 天。
- 密码和哈希不进日志或 payload；错误统一 code。
- 用户管理 API 仅管理员可用，首版不做管理页。

## Implementation steps





1. 先写错误密码、过期 token、强改密、刷新旋转和票据重放的失败测试。
2. 迁移 users 并实现 identity service/routes/middleware。
3. 更新 OpenAPI 和路由守卫所需契约。

## Dependencies and boundary





- 依赖：m1-03, m1-04
- 交付边界：不做注册、OIDC、多租户和用户管理界面。

## Verification





```sh
pnpm test:api -- tests/identity
pnpm test:db
pnpm test:db:mysql
pnpm contract:check
```

- 未登录业务 API 401；must_change_password 时 403 PASSWORD_CHANGE_REQUIRED。
- 票据消费后重放 401；双方言迁移通过。

## Acceptance





- 登录/刷新/登出/改密全链路可自动验证。
- 所有业务路由都有鉴权依赖。

## Gates and CI





- 鉴权契约与双方言测试进入 CI。

## Non-goals

- No SSE transport or user UI.
