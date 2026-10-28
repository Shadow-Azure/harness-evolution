# m5-10 Placeholder Eval

English | [中文](m5-10-placeholder-eval.md)

```yaml flow
kind: issue
id: m5-10
milestone: m5
depends:
  - m5-09
priority: P0
status: done
scope:
  - apps/api/**
  - packages/contracts/**
  - fixtures/**
  - docs/**
  - plans/2026-10-28-pr143-review.md
  - .agents/flow/**
  - .agents/notes/**
adr:
  - ../../notes/implemented/architecture/2026-10-28-placeholder-evaluation-loop.md
github:
  number: 59
  url: https://github.com/Shadow-Azure/harness-evolution/issues/59
```

## Background





m5-10 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m5-10 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [07 §5.7 评测接入](../../../plans/fullstack-design/07-backend-implementation.md)
- [07 §5.8 应用终评](../../../plans/fullstack-design/07-backend-implementation.md)
- [01 §4.3 自动逐轮](../../../plans/fullstack-design/01-architecture.md)

## Implementation





- 实现 eval gateway 接口、占位评分、eval_poller 每 5 分钟轮询、completed→apply、failed/timeout→blocked 和重启恢复

## Implementation steps





1. 写 fake gateway、到期扫描、超时和重启失败测试
2. 实现 poller/apply/finalize
3. 验证无人工 advance

## Dependencies and boundary





- 依赖：m5-09
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m5-10-placeholder-eval
pnpm test:db
```

- 占位 run 自动逐轮
- eval 完成后进入下一轮或终评

## Acceptance





- 状态流转可恢复且 candidate 可追溯

## Gates and CI





- poller gate、state tests、fake gateway tests

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
