# Agent Note: 占位评测与自动逐轮闭环

Status: implemented

[English](2026-10-28-placeholder-evaluation-loop.en.md) | 中文

## Problem

Git candidate 发布后，轮次只停在 `evaluating/pending`。服务没有可调用的评测 gateway、没有独立 poller，也没有 persisted `next_poll_at`、apply 与 finalize handler。结果是候选虽然真实存在，自动闭环仍无法在进程重启后继续，run 也无法从评测结果推进到下一轮或终态。

## Decision

`EvalGateway` 以 `submit/get_status/get_result` 三个异步方法为稳定接缝；请求、提交、状态、结果为不可变内部模型，gateway 只由 run 创建期冻结的 `eval_config` 构成。V1 `FakeEvalGateway` 不依赖内存任务：外部 id 由 run、round 与 candidate commit 推导，状态和分数由冻结配置决定，因此进程重启后仍能解释同一 id。

`EvolutionEvalSubmitter` 只在完整模式、run running、round evaluating 且 candidate 已真实推送时提交评测；已存在 `eval_external_id` 时直接复用，不重复提交。提交与 round 的 external id、evaluating 状态、attempt、start time、next poll deadline、run 的聚合 `eval_status` 在同一事务落库。本地 candidate 的 `skipped` 与 cluster-only 都不进入评测。

`EvolutionEvalPoller` 是独立进程级轻量循环，不占 JobRunner worker。每轮只按 `status=evaluating AND eval_status=evaluating AND next_poll_at<=now` 扫描到期轮次；queued/running 只把下一次 deadline 推后 5 分钟；completed 的结果连同 `eval_current/eval_candidate` 投影只保存一次；failed、timeout、请求异常或 malformed result 进入脱敏的 `blocked(eval)`，不会自动重新提交。超时兜底按 `eval_started_at + HE_EVAL_TIMEOUT_SECONDS` 判断，即使 gateway 仍报告 running 也优先生效。

自动后续任务以持久事实为准，不依赖进程内回调恰好成功。同一 poller 每轮还会扫描“评测已完成但尚未进入 applying”的轮次，以及“全部轮次已终结但 run 仍在 running”的 run；缺失的 `evolution_apply`、下一轮 `evolution_advance` 或 `evolution_finalize` 会被幂等补投。follow-up 入队失败只记日志并留待下次扫描；已存在活动阶段时把它当作已覆盖，不重复创建。因此进程在结果落库、终态决策或 JobRunner terminal hook 之间退出时，重启后的扫描仍能继续闭环。单个 malformed 外部状态只能阻塞自己的轮次，不能中止同批其他到期 run。

`EvolutionApplyService` 只消费持久化 completed result，用 external verdict 复用真实 accept/reject candidate 边界。accepted/rejected 都是吸收态，重复 apply 不会再次改写 candidate 或 run 分支。accept/reject 在同一事务推进 run `progress_unit`，因此最后一个轮次结束后 cursor 恰好到达终评前序。

`EvolutionApplyService` 严格服从 external verdict，但决策文案按真实分差描述“高于/低于/等于”；因此外部 verdict 接纳一个分数下降的候选时，final 的布尔 verdict 仍表示“是否存在分数组提升的已接纳轮次”，不会反过来改写 external verdict。terminal lifecycle 在 prepare、advance、apply 成功后查询持久轮次：存在活动轮次时不排队；存在 pending 时排队下一轮 advance；全部轮次 accepted/rejected/skipped 时只排队一个 finalize。`EvolutionFinalizeService` 从各轮结果生成占位 final row，再校验并只 fast-forward 发布 run 分支，最后把 run 置为 completed；final 写入、workspace 重建或最终 push 失败时保留已有终评与轮次事实并进入可重试 blocked，不伪造 completed。`HE_GIT_PUSH=false` 时仍完成本地终态，但 push status 为 skipped。

## Alternatives considered

在 JobRunner handler 内 sleep 会占住唯一 worker，并使重启后的定时状态消失。仅依赖 gateway 内存状态无法恢复进程重启后的评测。让 poller 直接执行 git 会扩大其职责并引入全局 worker 竞争。把 apply 决策直接写成固定 accept 会绕过真实 amend、candidate force-with-lease、run fast-forward 和 reject 清理边界，因此仍复用 m5-09 candidate service。

## Consequences

占位 run 现在可从 prepare 自动推进到每轮 candidate、push、evaluation、apply，再到下一轮和终评；刷新或重启不会重复提交已有 eval id，也不会因扫描重复排队 apply。评测分数和 patch 仍是占位事实，真实外部评测、真实 patch 与评分口径不在本切片。自动退避、blocked sweeper、崩溃任务恢复和实时 SSE 重连仍由 m5-11 负责。
