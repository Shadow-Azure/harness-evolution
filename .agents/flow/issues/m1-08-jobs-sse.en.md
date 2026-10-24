# Jobs runner, SSE bus, and one-time tickets

English | [中文](m1-08-jobs-sse.md)

```yaml flow
kind: issue
id: m1-08
milestone: m1
depends:
  - m1-06
priority: P1
status: backlog
scope:
  - apps/api/**
  - apps/api/alembic/**
  - packages/contracts/**
  - scripts/**
  - .github/workflows/ci.yml
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr:
adr: []
github:
  number: 31
  url: https://github.com/Shadow-Azure/harness-evolution/issues/31
```

## Background





轨迹同步和后续自进化都需要持久任务状态、重启恢复与实时通知，不能用进程内 fire-and-forget。

## Goals





- 建立 job_runs 迁移、串行 worker、同 kind/ref 去重和重启 interrupted 恢复。
- 实现内存事件总线、seq/Last-Event-ID 补发、心跳和 topic 过滤。
- SSE 只接受已登录用户换取的一次性票据。

## Design authority





- [04 后端架构](../../../plans/fullstack-design/04-backend-architecture.md)

## Implementation





- REST 是事实源，事件只做通知；run 事件可从库回放。
- 票据绑定 topics/cursor，消费即作废，60 秒过期。
- lifespan 关闭时取消任务、关闭队列并 dispose engine。

## Implementation steps





1. 先写并发去重、异常捕获、重启恢复、断线补发和票据重放的失败测试。
2. 迁移 job_runs 并实现 jobs/events/SSE 路由。
3. 生成任务与事件契约。

## Dependencies and boundary





- 依赖：m1-06
- 交付边界：不实现 sync 或 evolution 具体 job，只提供执行与通知基座。

## Verification





```sh
pnpm test:api -- tests/jobs
pnpm test:api -- tests/events
pnpm contract:check
```

- 并发请求只产生一个活跃 job；重启后 running 被标 interrupted。
- 断线后 Last-Event-ID 只补发缺失事件，旧票据重放失败。

## Acceptance





- 任务状态、错误摘要和时间戳可查询。
- SSE 订阅/补发/心跳/作废全部通过。

## Gates and CI





- 任务与 SSE 测试进入 CI。

## Non-goals

- No Celery or multi-instance queue.
