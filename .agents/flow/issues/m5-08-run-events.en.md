# m5-08 Run Events

English | [中文](m5-08-run-events.md)

```yaml flow
kind: issue
id: m5-08
milestone: m5
depends:
  - m5-01
  - m5-07
priority: P0
status: backlog
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - fixtures/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 57
  url: https://github.com/Shadow-Azure/harness-evolution/issues/57
```

## Background





m5-08 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m5-08 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [05 §4.15 执行日志](../../../plans/fullstack-design/05-api-design.md)
- [06 §5.7 events](../../../plans/fullstack-design/06-database-design.md)
- [07 §5.9](../../../plans/fullstack-design/07-backend-implementation.md)

## Implementation





- 实现 evolution_run_events 追加、events API、阶段/候选/push/eval/blocked/retry 事件和日志面板
- 错误脱敏 8KB

## Implementation steps





1. 写事件持久化、重启回放、脱敏和截断失败测试
2. 实现 service/API/panel

## Dependencies and boundary





- 依赖：m5-01, m5-07
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m5-08-run-events
pnpm test:db
pnpm test:web
pnpm test:e2e
pnpm contract:check
```

- 刷新后事件顺序完整
- 密钥样例被替换
- 超长 detail 截断

## Acceptance





- 失败原因可在 UI 直接定位

## Gates and CI





- events gate、安全脱敏测试、E2E

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
