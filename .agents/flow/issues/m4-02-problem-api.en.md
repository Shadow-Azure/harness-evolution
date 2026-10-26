# m4-02 Problem Api

English | [中文](m4-02-problem-api.md)

```yaml flow
kind: issue
id: m4-02
milestone: m4
depends:
  - m4-01
priority: P0
status: in-progress
scope:
  - apps/api/**
  - packages/contracts/**
  - fixtures/**
  - tests/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
  - reports/**
adr: []
github:
  number: 47
  url: https://github.com/Shadow-Azure/harness-evolution/issues/47
```

## Background





m4-02 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m4-02 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [05 §4.6–4.7 API](../../../plans/fullstack-design/05-api-design.md)
- [05 §5 深链](../../../plans/fullstack-design/05-api-design.md)
- [06 §7.4 口径](../../../plans/fullstack-design/06-database-design.md)

## Implementation

- Adds five read-only endpoints for Session problems/probes, problem detail, attribution, and probe detail.
- Combines Session title, Agents/events, external problems, attribution, and probes in one database snapshot and reuses tree anchor semantics.
- The optional `sessionId` validates deep-link ownership; mismatch returns `409 BAD_CASE_SESSION_MISMATCH`, absence returns stable 404.
- Missing attribution returns the `unanalyzed` placeholder; all five display states share the same public `analysis` object.

## Implementation steps





1. 写列表、详情、跨会话 409、probe 反查失败测试
2. 实现 service/routes
3. 生成契约

## Dependencies and boundary





- 依赖：m4-01
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m4-02-problem-api
pnpm test:api
pnpm test:db
pnpm contract:check
pnpm test:web
pnpm test:e2e
```

- API 测试通过且 contract:check 无漂移
- 固定五态响应可精确断言

## Acceptance





- ID 深链安全且归因状态合并正确

## Gates and CI





- route gate、contract gate、双方言测试

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
