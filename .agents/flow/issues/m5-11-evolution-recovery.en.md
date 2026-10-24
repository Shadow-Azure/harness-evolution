# m5-11 Evolution Recovery

English | [中文](m5-11-evolution-recovery.md)

```yaml flow
kind: issue
id: m5-11
milestone: m5
depends:
  - m5-10
priority: P0
status: backlog
scope:
  - apps/api/**
  - apps/web/**
  - fixtures/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 60
  url: https://github.com/Shadow-Azure/harness-evolution/issues/60
```

## Background





m5-11 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m5-11 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [07 §5.8.1 阻塞重试](../../../plans/fullstack-design/07-backend-implementation.md)
- [05 §4.14 SSE](../../../plans/fullstack-design/05-api-design.md)
- [06 §5.7 events](../../../plans/fullstack-design/06-database-design.md)

## Implementation





- 实现 blocked_sweeper 1/5/15 分钟退避、retry 仅 blocked、进程恢复、SSE 运行联动和完整占位闭环冒烟

## Implementation steps





1. 写三次退避、不可重试错误、重启和断线补发失败测试
2. 实现 sweeper/retry
3. E2E 走完准备→候选→评测→接纳/拒绝

## Dependencies and boundary





- 依赖：m5-10
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m5-11-evolution-recovery
pnpm test:db
pnpm test:web
pnpm test:e2e
```

- E2E run 自动结束且日志完整
- 断线重连恢复进度

## Acceptance





- 失败可恢复，run 分支和历史一致

## Gates and CI





- E2E full placeholder、sweeper tests、events replay

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
