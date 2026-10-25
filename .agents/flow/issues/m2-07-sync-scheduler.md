# m2-07 sync scheduler

[English](m2-07-sync-scheduler.en.md) | 中文

```yaml flow
kind: issue
id: m2-07
milestone: m2
depends:
  - m2-06
priority: P0
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - fixtures/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - reports/**
  - .github/workflows/ci.yml
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 39
  url: https://github.com/Shadow-Azure/harness-evolution/issues/39
```

## 背景

本地 payload 导入和幂等重放已经可用，但系统仍缺少定时发现待处理数据、管理员手动触发与跨触发单飞保护。

## 目标

- 默认每 60 秒处理 pending payload，`0` 时只允许 admin 手动触发。
- scheduler 与手动触发共用 durable `sync_lock`、进程内锁和串行 JobRunner。
- 顶栏展示真实 pending 状态，并允许 admin 立即处理；sync 不使用 SSE。

## 设计依据

- [01 §4.3.4 后台定时](../../../plans/fullstack-design/01-architecture.md)
- [04 §7 任务](../../../plans/fullstack-design/04-backend-architecture.md)
- [06 §3.7 sync_lock](../../../plans/fullstack-design/06-database-design.md)

## 实现内容

- `sync_lock` 采用 30 分钟 TTL；活动 job 即使 TTL 已过仍复用，terminal/missing job 的锁可回收。
- job 与锁在同一事务创建；handler 由 JobRunner 串行执行，terminal hook 按 jobId 释放匹配锁。
- `GET /api/acquisition/status` 返回 activeJobId、pending/processed、最近批次、last/next run 与脱敏错误。
- `POST /api/acquisition/sync` 仅 admin 可用；无 pending 时返回 `200 {jobId:null,status:"idle",reused:false}`。
- 亮色原型顶栏只显示安静 pending 摘要；admin 菜单提供“立即处理”，完成后轮询 job 并失效 sessions 查询。

## 实施步骤

1. 先写并发、TTL、异常/取消释放、无 pending、状态与顶栏失败测试。
2. 增加 `sync_lock` 迁移、repository、共享 coordinator 和 scheduler lifespan。
3. 注册 sync handler、生成契约并接入亮色顶栏。

## 依赖与交付边界

- 依赖：m2-06
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m2-07-sync-scheduler
pnpm test:db
pnpm test:web -- TopNav
pnpm test:e2e -- m1-shell
```

- scheduler/manual 并发只产生一个 job，失败方复用同一 jobId。
- 成功、失败与取消后匹配锁释放；terminal/missing job 的遗留锁可恢复。
- 无 pending 不建 job；manual 返回显式 idle。
- 390px 隐藏辅助 pending 状态，用户菜单与退出仍可用。

## 验收标准

- 同步可恢复且状态可观察
- 手动仅 admin 可用
- 窄屏与缺少 status 时壳层不破坏，不展示伪造计数。

## 门禁与 CI

- 并发测试、双方言 schema、契约生成、真实 Chrome 顶栏 E2E

## 非目标

- 不实现上游 pull
