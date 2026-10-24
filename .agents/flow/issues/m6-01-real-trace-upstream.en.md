# m6-01 Real Trace Upstream

English | [中文](m6-01-real-trace-upstream.md)

```yaml flow
kind: issue
id: m6-01
milestone: m6
depends:
  - m5-11
priority: P1
status: backlog
scope:
  - apps/api/**
  - plans/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 61
  url: https://github.com/Shadow-Azure/harness-evolution/issues/61
```

## Background





m6-01 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m6-01 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [05 §10 上游契约](../../../plans/fullstack-design/05-api-design.md)
- [04 §5 数据接缝](../../../plans/fullstack-design/04-backend-architecture.md)
- [09 R9/R10](../../../plans/fullstack-design/README.md)

## Implementation





- 将 HttpApiSource 接到真实上游，验证凭据注入、按需 pull、分页、失败隔离和版本监控
- PR CI 仍用 mock

## Implementation steps





1. 用环境凭据做 opt-in 集成测试
2. 实现健康/漂移日志和手动重放
3. 保持 fixtures CI

## Dependencies and boundary





- 依赖：m5-11
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m6-01-real-trace-upstream
pnpm test:db
```

- 本地/受控环境真实 pull 成功
- CI 不访问真实上游

## Acceptance





- 上游故障不阻塞 payload 表路径

## Gates and CI





- integration opt-in gate、contract monitor tests

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
