# Agent Note: 评测超时按执行时间计费

Status: implemented

[English](2026-11-27-eval-timeout-execution-billing.en.md) | 中文

## Problem

自进化 run 的评测此前从提交时刻开始计一个固定的 2 小时预算，且验证集基线、逐轮候选、测试集基线与测试集终评共用同一个上限。平台排队、启动准备与跨 run 容量预留都被算作执行时间：生产 run 的测试集基线在排队并执行超过 2 小时后被误判超时，候选评测在排队 100 分钟后刚开始执行也被同一时钟判处；验证集 mini-set 与留出测试集的规模差异同样没有体现在预算上。

## Decision

`EvalStatus` 暴露平台的 `started_at` 与 `progress.percent`，两者都可缺失。poller 的过期判定拆成两条时钟：执行预算从平台 `running` 的 `started_at` 起算，平台未返回时回退到 HE 的 `eval_started_at`；排队预算从 `eval_started_at` 起算，只用于 `queued` 的兜底。`HE_EVAL_TIMEOUT_SECONDS`（默认 2h）继续覆盖验证集基线与逐轮候选，新增 `HE_EVAL_TEST_TIMEOUT_SECONDS`（默认 6h）覆盖测试集基线与测试集终评，新增 `HE_EVAL_QUEUE_TIMEOUT_SECONDS`（默认 6h）给任何评测的排队兜底。`eval_polled` 与 `eval_timeout` 事件补 `kind`、`startedAt`、`elapsedSeconds`、`queueSeconds`、`progressPercent`，让运维直接区分排队与执行。暂停时间仍从两条时钟中扣除。

评测门控与终评语义不变：候选仍须严格优于基线，测试集终评仍以测试集基线为 `init_score`；本决策只改时间计量与预算分档。相关门控与终评语义见 [SkillOpt 式基线门控与测试集终评](2026-11-25-baseline-gate-test-final.md)。

## Alternatives considered

继续用提交时刻计费并整体放大上限：排队与执行仍无法区分，异常排队会吃掉执行预算，验证集与测试集也无法各自取值。只按评测类型调大全局值：测试集基线不再在 2 小时处误杀，但候选在排队 100 分钟后仍只剩 20 分钟实际执行预算。要求评测平台提供排队 SLA 或容量预留：属于 ai-eval-platform 的调度问题，本仓库无法验证，也超出本 issue 边界。新增 HE 数据库列存执行起点：平台已提供权威 `started_at`，落库会引入第二个事实源与迁移成本。

## Consequences

旧平台响应缺少 `started_at` 时回退到原来的提交时刻计时，行为与决策前一致，不阻塞发布。`eval_paused_seconds` 仍是粗粒度累计值；暂停若发生在执行开始前，也会从执行预算中扣除，因此只会少算、不会多算执行时间。Run 详情与 SSE 的事件 payload 变大，前端展示字段不变。测试集预算按 6 小时保守取值，后续可按平台实际吞吐调整。
