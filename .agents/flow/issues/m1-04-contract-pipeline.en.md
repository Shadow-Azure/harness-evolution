# OpenAPI contract generation and drift gate

English | [中文](m1-04-contract-pipeline.md)

```yaml flow
kind: issue
id: m1-04
milestone: m1
depends:
  - m1-02
priority: P0
status: backlog
scope:
  - apps/api/**
  - packages/contracts/**
  - scripts/**
  - package.json
  - .github/workflows/ci.yml
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 27
  url: https://github.com/Shadow-Azure/harness-evolution/issues/27
```

## Background





React 手写契约必须换成 OpenAPI 单源，否则 FastAPI 与 Vue 会持续漂移。

## Goals





- 从 FastAPI 导出 OpenAPI 快照并生成 packages/contracts TypeScript 类型。
- 提供 contract:generate/check 命令和生成物禁改检查。
- 用真实响应做编译期契约测试。

## Design authority





- [04 后端架构](../../../plans/fullstack-design/04-backend-architecture.md)

## Implementation





- Pydantic DTO 使用 extra=forbid 与 camelCase 序列化。
- 生成物放入 packages/contracts/src/generated，不手改。
- CI 在 build 前执行 check，diff 即失败。

## Implementation steps





1. 为 health 和错误响应建立 OpenAPI 快照测试。
2. 接入 openapi-typescript 并生成类型。
3. 添加 pnpm contract:generate/check 与元测试。

## Dependencies and boundary





- 依赖：m1-02
- 交付边界：只覆盖已存在 health/error 契约；不预生成未实现接口。

## Verification





```sh
pnpm contract:check
pnpm typecheck
```

- 人为改生成物时 contract:check 失败并给出重生成命令。
- 前端类型可被真实 health JSON 赋值。

## Acceptance





- OpenAPI 快照和 TS 生成物纳入版本控制。
- 无手写重复接口类型。

## Gates and CI





- contract:check 进入静态 CI。

## Non-goals

- No GraphQL or runtime validator adoption.
