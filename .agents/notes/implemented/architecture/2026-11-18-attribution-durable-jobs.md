# Agent Note: 归因持久化任务与独立执行通道

Status: implemented

[English](2026-11-18-attribution-durable-jobs.en.md) | 中文

## Problem

归因从固定规则替换为真实 LLM 与 Agent 后会成为长耗时、可限流且可能部分失败的工作。如果 Run prepare 继续在全局串行 worker 内直接逐条执行，慢调用会阻塞同步和其他 Run；手工、定时与失败重试各自实现又会产生不同的幂等、缓存和恢复语义。管理员还需要知道执行是否前进，但观测面不能泄露原始 Trace、Skill 正文或凭据。

## Decision

以 `job_runs` 作为归因批次唯一任务真值，增加持久化 claim、租约、最大尝试次数与取消标志，并为 `attribution_batch` 分配独立且有上限的 handler lane。Run prepare、管理员手工启动、正式调度入口和 retry 都调用同一 `AttributionJobService.submit`，以 Run ID 作为活跃任务幂等坐标；不新增 `attribution_only` Run mode。Runner 在一个 Session 上下文批次准备完成后以 Badcase 为单位有界并发，单条失败不回滚已写报告，重试沿用同一任务审计行并依靠 candidate pointer 只补未完成项。任务结果只保存 executor、Skill revision、批次上下文 hash、数量、缓存、延迟、Token、warning 与证据覆盖率，Web 对 viewer 开放读取，对 space admin 开放启动、取消和重试。

候选快照确定批次范围，逐条关联的报告确定已产出数量与分类，页面可在批次完成前核对进度。作业进度保留数值型 Token 用量，历史脱敏值显示为未知。

## Alternatives considered

新增 `attribution_only` Run mode 会把同一候选快照和阶段状态复制到第二套生命周期，因此保留 prepare 为主编排并把归因下沉成可被多个入口共享的持久化批次。让归因继续竞争全局 worker 锁实现更少，但真实模型延迟会把无关同步任务排在其后。每次重试创建新任务行更容易统计尝试，却会削弱一次逻辑执行的审计身份并放大重复调度，所以同一行递增 attempt，历史状态和最终结果仍可追踪。

## Consequences

进程启动时会把未完成归因释放为 queued，worker 通过短租约和心跳持有 claim；租约与尝试上限防止无限自动执行。取消会传播到正在运行的批次及尚未完成的 Badcase 子任务；已提交报告保持可复用。当前离线执行器报告 Token 为零，真实内网 adapter 必须通过 executor response 回传用量；上下文观测只保存各 case manifest 上下文 hash 的批次哈希。部署升级必须先运行 Alembic `0025_attribution_job_leases`，管理员可在 Run 的“对象归因”步骤查看进度和脱敏错误并操作失败任务。
