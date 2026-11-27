# Agent Note: SkillOpt 式基线门控与测试集终评

Status: implemented

[English](2026-11-25-baseline-gate-test-final.en.md) | 中文

## Problem

真实评测平台只提供测量值与指标方向，不提供 accept/reject。此前 HE 的逐轮裁决直接采信网关返回的 `externalVerdict`，终评只是把各轮验证分汇总成 `init_score` 与 `best_score`，既没有「初始版本评一次作为基线」，也没有独立的留出测试集验收。这样同一个候选在评分噪声下可能被接纳，最终结论也无法回答「最终版本是否比初始版本更好」。

## Decision

评测网关 `get_result` 只返回 `EvalMeasurement`（主指标值、指标方向与原始指标项）。裁决固定在 service 层 `service/evolution/eval_gate.py`：轮次 N 的基线取最近一个已接纳轮的候选分，没有已接纳轮时取运行级 `validation_baseline` 的分数；候选必须按指标方向严格优于基线才接纳，平票拒绝。接纳后基线自然顺延到该轮候选分，拒绝时 run 分支与基线都不动。

运行级评测存进新的 `evolution_evaluations` 表，`kind` 为 `validation_baseline`、`test_baseline` 与 `test_final`，字段与轮上的评测列同构。`evolution_advance` 在发布第 1 轮前只提交验证集基线；测试集基线与测试集终评都留到全部轮次终态后的 `evolution_finalize`，二者并发在途。`evolution_apply` 在验证集基线未完成时只返回未应用，由 poller 重新入队，绝不提前裁决。最后一个迭代终结后 `evolution_finalize` 同时提交测试集基线与测试集终评，两者都完成后才写 `evolution_finals`：`init_score` 是测试集基线分、`best_score` 是测试集终评分，`verdict` 要求存在接纳轮且终评分严格优于测试集基线。

没有接纳轮时 `test_final` 不再回退 `base_commit`：终评环节先在 run 分支创建一个不修改任何 skill 文件的空结果 commit，消息带 `Harness-Run-Id`、`Harness-Verdict: no-acceptance` 以及验证集初始/最佳分、指标和各轮决策；推送后它作为测试集终评对象，哈希存 `evolution_runs.result_commit`，重试复用同一 commit。poller 只在两个测试集评测都不在途时重新入队 `evolution_finalize`。

平台侧错误按可重试性区分：401/403/404/422 判不可重试并进入 `blocked(stage=eval)`，错误信息带平台错误码；5xx、429 与网络错误标为可重试，poller 只推迟下次轮询，仍受 2h 超时封顶。基线或终评失败同样走 `blocked(stage=eval)`，`/retry` 先清理失败行再重新提交，不重跑已接纳的迭代。

launch 的 `asset_override` 必须指向平台运行时生成的资产路径，而不是 HE 目标仓库的源码路径。OpenSpec 快照把对象放在 `skills/`、`agents/`、`commands/`，平台执行 `codespec init` 后发布为 `.claude/skills/`、`.claude/agents/*.md`、`.claude/commands/`；网关按目标类型做这层映射并显式带 `asset_types`，避免平台无法推断类型或源码与生成资产路径冲突。

## Alternatives considered

让平台继续返回 verdict：平台契约不提供，且会重新把接纳规则耦合进每个平台子类。把基线存在 `evolution_rounds` 上：基线与终评不属于任何轮，复用轮表会破坏 `(run_id, seq)` 唯一性与轮生命周期。候选结果一落库就用当时的基线裁决：基线未完成时只能猜一个分数，等于把观测时序当作结论。只在真实平台启用基线与终评：会让 fake 模式与生产走不同裁决路径，测试无法覆盖真实门控。测试集终评读取各轮验证分：无法回答留出测试集上的独立验收问题。把测试集基线留在启动路径：运行取消、没有接纳轮或提前失败时仍会消耗测试集容量，并把测试集失败面提前耦合进第 1 轮。无接纳时继续回退 `base_commit`：终评对象与初始版本完全相同，无法区分「运行没有产出」与「最终版本就是初始版本」。

## Consequences

`evolution_finals.best_score` 的含义从「各轮最高验证分」改成「测试集终评分」，前端字段不变但数值口径变化；这是 SkillOpt 对照的直接结果。运行级评测需要迁移 `0033` 与双方言仓储；无接纳轮结果 commit 需要迁移 `0036` 的 `evolution_runs.result_commit`。旧 run 在部署后首次推进或终评时补交基线，已完成的轮次不受影响。测试集只在终评阶段出现，启动阶段不再占用平台容量；`/retry` 只重提失败的测试集评测，已完成的不重置。平台 `partial` 状态按最低完成率 50% 护栏判完成或失败，`paused_budget` 直接失败并给出可操作信息。逐轮幂等键加入尝试次数，平台侧失败后重试不会重放同一个评测。
