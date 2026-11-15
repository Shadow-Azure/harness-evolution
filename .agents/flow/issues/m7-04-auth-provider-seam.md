# AuthProvider 接缝与唯一管理员边界

[English](m7-04-auth-provider-seam.en.md) | 中文

```yaml flow
kind: issue
id: m7-04
milestone: m7
depends:
  - m7-02
  - m7-03
priority: P0
status: in-progress
scope:
  - apps/api/app/service/identity/**
  - apps/api/app/api/auth.py
  - apps/api/app/api/users.py
  - apps/api/app/config.py
  - apps/api/app/errors.py
  - apps/api/app/db/crud/users.py
  - apps/api/app/db/models/users.py
  - apps/api/app/middleware/auth.py
  - apps/api/app/middleware/rate_limit.py
  - apps/api/tests/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - deploy/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr:
  - ../../notes/implemented/architecture/2026-11-15-auth-provider-seam.md
github:
  number: 225
  url: https://github.com/Shadow-Azure/harness-evolution/issues/225
```

## 背景

后续 Cookie 或 SSO 接入必须只替换身份提供方，不应重写业务权限和前端契约。

## 目标

- 建立 AuthProvider、ProviderRegistry、会话桥和 callback 占位。
- 维持唯一全局管理员和禁止注册。
- 外部身份映射失败时不自动建号。

## 设计依据

- [07 §8.2.1](../../../plans/fullstack-design/07-backend-implementation.md)：AuthProvider 接缝。
- [05 §4.16](../../../plans/fullstack-design/05-api-design.md)：鉴权端点与错误码。

## 实现内容

- password provider 保持现有行为。
- HE_AUTH_PROVIDER 对 cookie/oidc 未配置实现 fail fast。
- callback 覆盖 400/401/403/501/502 稳定错误码。
- 公开回调、稳定错误码与启动校验需要触碰 API 装配、错误码、中间件和 API 测试，故 scope 覆盖这些文件；配置说明、OpenAPI 与 Agent Note 同 PR 更新。

## 实施步骤

1. 先写 provider 选择和 callback 失败测试。
2. 拆分 password provider 与会话桥。
3. 更新配置、OpenAPI 和迁移说明。

## 依赖与交付边界

- 依赖：m7-02、m7-03
- 交付边界：只预留接缝，不实现真实 IdP。

## 独立验证

```sh
pnpm test:api -- tests/identity; pnpm contract:check
```

- password 登录不回归。
- 非法 provider 启动失败。
- callback 未配置返回 501 且不建用户。

## 验收标准

- 业务代码不感知外部身份来源。
- 全局管理员唯一约束由服务端强制。

## 门禁与 CI

- 身份、契约、启动配置与 flow 门禁。

## 非目标

- 不接入生产 Cookie/SSO。
- 不开放注册。
