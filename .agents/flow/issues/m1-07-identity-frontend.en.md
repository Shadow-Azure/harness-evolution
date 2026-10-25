# Login, forced password change, and frontend auth

English | [中文](m1-07-identity-frontend.md)

```yaml flow
kind: issue
id: m1-07
milestone: m1
depends:
  - m1-05
  - m1-06
priority: P0
status: in-progress
scope:
  - apps/web/**
  - packages/contracts/**
  - .github/workflows/ci.yml
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
  - reports/**
  - pnpm-lock.yaml
adr: []
github:
  number: 30
  url: https://github.com/Shadow-Azure/harness-evolution/issues/30
```

## Background





业务页面必须在真实 JWT 下运行，且 token 过期/首登改密不能让用户停留在错误页。

## Goals





- 实现登录页、强制改密页、auth store、Bearer 注入和路由守卫。
- 处理 401 自动刷新一次、redirect 回跳、退出清态和错误态。
- 为顶栏用户区提供当前用户与退出。

## Design authority





- [03 前端架构](../../../plans/fullstack-design/03-frontend-architecture.md)
- [05 接口设计](../../../plans/fullstack-design/05-api-design.md)
- [08 前端实现](../../../plans/fullstack-design/08-frontend-implementation.md)

## Implementation





- access token 只存内存；refresh cookie 由后端管理。
- query/mutation 失败按统一错误模型展示，不弹原生 alert。
- 每个守卫分支可由 MSW 响应驱动测试。

## Implementation steps





1. 先写未登录、redirect、强改密、401 刷新、登出的组件/组合式失败测试。
2. 实现 api/auth、store、http、守卫和页面。
3. 接 OpenAPI 类型并更新 CI 测试。

## Dependencies and boundary





- 依赖：m1-05, m1-06
- 交付边界：不做用户管理页、记住密码和注册。

## Verification





```sh
pnpm test:web
pnpm lint:web
pnpm typecheck:web
pnpm build
pnpm verify:web-style
pnpm verify:bundle
```

- 全部测试与覆盖率门禁通过；未登录访问 /sessions 跳登录并回跳；过期 token 自动刷新后重放。
- 首登被改道改密，成功后放行；Element Plus 保持按需 chunk。

## Acceptance





- 三种鉴权状态和登录失败态都有明确 UI。
- 退出后内存态与 query 缓存清空。

## Gates and CI





- 前端鉴权测试进入 CI。

## Non-goals

- No user CRUD UI.
