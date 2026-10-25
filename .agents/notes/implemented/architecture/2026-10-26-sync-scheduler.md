# Agent Note: 同步调度与单飞锁

Status: implemented

[English](2026-10-26-sync-scheduler.en.md) | 中文

## Problem

scheduler 与 admin 手动触发可以同时发现 pending payload。如果 job 先落库、锁后获取，或 handler 只依赖内存锁，进程崩溃与并发请求会产生孤儿 job、重复重放或永久卡住的同步状态。

## Decision

`sync_lock` 是跨进程单飞真值，固定 `name=sync`，TTL 默认 30 分钟；进程内 `asyncio.Lock` 只作为 V1 快速兜底。sync job 和锁在同一事务创建，任何主键冲突都会整体回滚。活动 job 即使 TTL 已过仍然复用；关联 job 缺失或 terminal 时才回收遗留锁。

Scheduler 与手动 API 共用一个 coordinator。默认每 60 秒检查 pending，`0` 关闭自动 tick。无 pending 不建 job；手动请求返回显式 `200 idle`，不伪造 jobId。正常 sync run id 复用 job id，`ref_id` 因而同时保留 job provenance 和批次关联；进程重启重排时保留旧审计并把旧 run 标为 interrupted，替代 job 使用新的 replay run id。进度写 `job_runs.progress`，不经过 SSE。JobRunner terminal hook 在 completed、failed 或 interrupted 落库后，先将仍为 running 的对应 sync run 终结为同一异常状态，再按 jobId 释放锁。

亮色原型顶栏只显示真实 pending 摘要和最近批次；admin 菜单才出现“立即处理”。操作后轮询 durable job，终态时失效 sessions 查询。status 不可用时隐藏摘要，不显示假计数。

## Alternatives considered

- 只用内存锁：进程崩溃或未来多实例会失去互斥，拒绝。
- 先创建 job，再异步补锁：会产生无锁运行窗口，拒绝。
- scheduler 与 manual 各自实现触发：并发规则容易分叉，拒绝。
- 用 SSE 推 sync 进度：设计明确 sync 只走 REST 轮询，拒绝。

## Consequences

单实例部署仍依赖进程内 JobRunner；多实例 worker 需要在同一 `sync_lock`/`job_runs` 契约上增加 `SKIP LOCKED` 或外部执行器。TTL 只处理崩溃遗留，不用于抢占仍在运行的 job。Admin 手动触发返回 current job 的复用 id；普通用户只能读取状态。重启后的 replacement job 与旧 batch 使用不同 id，审计关系通过各自 `ref_id` 保留。
