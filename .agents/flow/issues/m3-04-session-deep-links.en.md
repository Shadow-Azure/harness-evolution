# m3-04 Session Deep Links

English | [中文](m3-04-session-deep-links.md)

```yaml flow
kind: issue
id: m3-04
milestone: m3
depends:
  - m3-03
priority: P0
status: backlog
scope:
  - apps/web/**
  - packages/contracts/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 44
  url: https://github.com/Shadow-Azure/harness-evolution/issues/44
```

## Background





m3-04 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m3-04 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [05 §5 深链契约](../../../plans/fullstack-design/05-api-design.md)
- [08 §6.2 深链状态](../../../plans/fullstack-design/08-frontend-implementation.md)
- [09 R6 风险](../../../plans/fullstack-design/README.md)

## Implementation





- 定义并实现 sessionId/agentId/证据/tab 参数解析与恢复
- 非法或跨会话 id 返回 409/页面错误
- 前进后退不丢状态

## Implementation steps





1. 写 query parser 和浏览器历史失败测试
2. 实现守卫与恢复
3. 验证新窗口打开

## Dependencies and boundary





- 依赖：m3-03
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m3-04-session-deep-links
pnpm test:db
pnpm test:web
pnpm test:e2e
```

- 深链测试通过
- 刷新/新窗口恢复同一位置
- 跨 session 409 可见

## Acceptance





- 深链可分享且无串会话

## Gates and CI





- query parser 单测、E2E、契约测试

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
