# m2-07 Sync Scheduler

English | [中文](m2-07-sync-scheduler.md)

```yaml flow
kind: issue
id: m2-07
milestone: m2
depends:
  - m2-06
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
  number: 39
  url: https://github.com/Shadow-Azure/harness-evolution/issues/39
```

## Background





m2-07 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m2-07 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [01 §4.3.4 后台定时](../../../plans/fullstack-design/01-architecture.md)
- [04 §7 任务](../../../plans/fullstack-design/04-backend-architecture.md)
- [06 §3.7 sync_lock](../../../plans/fullstack-design/06-database-design.md)

## Implementation





- 实现默认 60 秒 scheduler、admin 手动 sync、sync_lock 单飞、TTL 回收和顶栏状态接口
- 无 pending 跳过

## Implementation steps





1. 写 scheduler/manual 并发、TTL、异常释放和无 pending 的失败测试
2. 实现调度与 API
3. 接 job_runs 状态

## Dependencies and boundary





- 依赖：m2-06
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m2-07-sync-scheduler
pnpm test:db
```

- sync 并发只产生一个 job
- TTL 过期后可恢复
- 无 pending 不建 job

## Acceptance





- 同步可恢复且状态可观察
- 手动仅 admin 可用

## Gates and CI





- 并发测试、job gate、SSE 状态冒烟

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
