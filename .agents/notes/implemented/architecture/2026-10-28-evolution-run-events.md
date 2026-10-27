# Agent Note: 自进化事件回放与执行日志

Status: implemented

[English](2026-10-28-evolution-run-events.en.md) | 中文

## Problem

M1 的事件 projection 已能做 SQL 回放和中断通知，但 evolution 父表关系、资源授权、通用失败写入、REST 分页和运行详情日志界面仍缺失；`lastEventSeq` 只能返回硬编码零，刷新后的排障链路没有完整事实源。

## Decision

`evolution_run_events` 通过 `run_id` 外键归属 `evolution_runs`，并以 `(run_id, seq)` 作为稳定回放游标。`EvolutionRunEventService` 在追加前统一递归脱敏 JSON、消息和错误详情，覆盖 `HE_*`、URL userinfo、Bearer/Basic Authorization、密码与密钥字段，把 `error.detail` 按 UTF-8 截到 8KB，再持久化并发布带 `runId` 的 `run.event`；不可恢复异常、进程中断、可重试阻塞和恢复分别同步 run 状态并发布对应的 `run.failed/run.interrupted/run.blocked/run.resumed` 通知，`RunBlocked` 边界保证 patch、push、eval 的可重试失败不会冒充终态失败。REST `/runs/{rid}/events` 支持 `afterSeq`、`limit` 与 level 过滤，是刷新和重启后的唯一回放源，SSE 只负责通知。运行详情以真实 max seq 填充 `lastEventSeq`，日志 tab 从 REST 分页并支持过滤、错误折叠、手动刷新、滚动暂停、步骤和簇深链。

## Alternatives considered

继续只用内存 EventBus 会让刷新和重启丢失过程事实；直接从 raw stderr 建日志会泄露凭据且突破负载边界；让 SSE 事件充当历史源会受慢连接、队列淘汰和重连竞态影响。把脱敏分散在调用方会让未来 engine 事件绕过安全边界，因此安全处理集中在事件 service。

## Consequences

事件存储与 run 生命周期保持可审计、可回放和可级联清理，UI 能在失败后直接定位原因。单进程中的 seq 分配通过唯一约束冲突重试保证不漏号，但不承担跨实例高并发吞吐；写 run 状态与写事件仍是相邻事务，极端故障下可能出现状态和最后事件短暂分离，后续恢复切片需继续收敛。

