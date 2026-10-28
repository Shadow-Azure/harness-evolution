# Agent Note: 自进化阻塞恢复

Status: implemented

[English](2026-10-28-evolution-recovery.en.md) | 中文

## Problem

run 一旦进入 `blocked`，服务没有任何持久计时器会把它推回执行：push 的瞬时故障只能靠人反复刷新页面等待，进程重启后内存里的恢复意图全部消失，前端断线后也无法确认看到的 blocked 阶段、重试次数与下次时间是否仍是当前事实。缺的是一层只依据数据库事实工作的恢复语义——哪些失败该自动再试、哪些必须等人、重启和重连之后以什么为准。

## Decision

`EvolutionBlockedSweeper` 是 lifespan 启动的进程内轻量循环，每 30 秒扫描 `blocked_stage=push`、`next_retry_at<=now` 且 `retry_attempts<3` 的 blocked run，到点只投一个 `evolution_retry` job；它自己既不占 JobRunner 的全局串行锁，也不在 job handler 里 sleep，所以等待退避的时间不占用 worker，也不拖住其他 run 的阶段推进。自动退避只覆盖 push 的瞬时错误：首次失败后 1 分钟，之后 5 分钟、15 分钟，第 3 次自动重试仍失败就写 `next_retry_at=NULL`，把控制权交回人；认证、权限、分支保护、non-fast-forward 等永久错误从不进入自动阶梯。sweeper 每轮对每个 run 最多做一次 push，一轮扫描不会无界重试。

eval 与 patch 的阻塞不进入自动退避，只接受 `POST /runs/{rid}/retry`；手动重试先把 `retry_attempts` 归零，让后续失败重新从 1/5/15 分钟阶梯开始。路由只对 blocked run 放行，其余状态返回 `RUN_NOT_RETRYABLE`；同一 run 已有活动的 `evolution_retry` job 时复用该 job 并返回 `reused=true`，重复点击不会叠加新的队列项。

`EvolutionRetryService` 先清掉 blocked 并写 `run.resumed`，再按 `blocked_stage` 与现场耐久事实分发，而不是按阶段名盲目重跑。push 阶段若终评已落库就继续 finalize，若本轮已有已完成评测就交给 apply，否则只重推已持久化的 candidate 并补交评测。eval 阶段清空旧 external id 后重新 submit，旧 id 留在事件 payload 里可追溯。patch 阶段从 `patching` 重新生成，而不是跳到 push 或 eval 接着跑。自动与手动共用同一个 handler，区别只在手动会重置阶梯、自动必须命中 push 且每次只做一次 push。

进程重启把残留 running job 标为 interrupted 并写 `run_interrupted`，不自动续跑；只有 blocked run 的 `next_retry_at` 是跨重启的持久事实，由 sweeper 重新接手。于是“重启后继续”只发生在能从数据库重新推导的路径上，一条已经中断的执行链不会被悄悄接回半完成的 git 状态。

实时面以 `evolution_run_events.seq` 为游标：SSE 首连与重连都从该 seq 之后回放，再转入实时；游标失效时发 `reset`，前端重拉 REST 快照。前端只在 `preparing/running` 订阅，blocked 改走 5 秒轮询，completed/failed/interrupted 关闭流；`run.blocked` 与 `run.resumed` 只是通知，页面展示的阶段、次数与时间仍以 REST 快照为准。

## Alternatives considered

用高频 job 轮询或独立队列承担退避被否：前者让每个等待中的 run 反复排队，占住唯一 worker；后者为一个 30 秒的轻量扫描再引入一套调度与运维面。把重试计数放进内存被否：进程一退就丢失“已经退避到第几次”，重启后无法接着计时。让 eval 自动重试被否：评测失败通常意味着外部配置或实现本身有问题，自动重提只会放大成本并掩盖原因，人工修复后的显式重试才可控。对 interrupted job 自动续跑被否：中断点可能落在 git 写入的半完成状态，接回会制造无法解释的分支历史。全局常驻 SSE 被否：为已完成 run 长期持有连接与鉴权上下文，流量与权限面都不划算。

## Consequences

push 的自动退避与手动重试已交付：瞬时故障能让 blocked run 自行恢复，永久故障则稳定停住等人处理。真实 patch 与真实评测仍是占位，恢复层只保证已有持久事实被正确续接，不判断外部系统为何失败。sweeper 是进程内循环，多实例部署时需要单飞，V1 以单进程为前提；跨实例抢占要等 JobRunner 支持 `SKIP LOCKED` 之后再补。占位闭环本身的决策见[占位评测与自动逐轮闭环](2026-10-28-placeholder-evaluation-loop.md)。
