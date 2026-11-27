# 测试集基线与最终评测统一在终评环节执行

[English](bugfix-test-set-baseline-at-final.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-71
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/**
  - .github/**
adr: []
github:
  number: 656
  url: https://github.com/Shadow-Azure/harness-evolution/issues/656
```

## 背景

### 问题场景

基线门控（#620 / PR #622）目前在运行启动时并行提交验证集基线与测试集基线，全部迭代结束后再提交测试集终评。结果是自进化一启动，测试集模板就先跑一次；迭代过程中每轮候选只用验证集，但测试集在启动阶段已经被消耗一次。

测试集的定位是全部问题迭代完成后的最终独立验收。启动即跑测试集不符合这个定位，也带来三个实际问题：

- 测试集在迭代开始前就占用平台容量与费用；运行被取消、没有接纳轮或提前失败时，这次测试集基线仍已经发生。
- 测试集基线提交失败会把运行直接置为 `blocked(stage=eval)`，阻塞第 1 轮；测试集的失败面被提前耦合进启动路径。
- 平台运行列表在启动阶段就出现测试集模板的运行，容易被误认为迭代过程中也在跑测试集。

### 现状分析

- `EvolutionAdvanceService.handle` 在发布第 1 轮前调用 `submit_baselines`；`EvolutionEvalSubmitter.submit_baselines` 依次提交 `validation_baseline` 与 `test_baseline`，二者都跑在 `base_commit`。
- 逐轮候选的 purpose 是 `candidate`，`_project_id` 固定解析 `validationProjectId`；`testProjectId` 只用于 `test_baseline` 与 `test_final`，所以迭代过程中实际不会跑测试集。
- `EvolutionFinalizeService.handle` 在所有轮次终态后调用 `submit_baselines` 与 `submit_test_final`；`test_final` 跑在最后一个已接纳轮的 commit，没有接纳轮时回退 `base_commit`。
- `_test_final_values` 以 `test_baseline` 为 `init_score`、`test_final` 为 `best_score`，`verdict` 要求存在接纳轮且终评分严格优于测试集基线分。
- 现有测试（如 `apps/api/tests/bugfix-63-real-eval/test_run_evaluations.py` 与 `apps/api/tests/m5-11-evolution-recovery/test_full_placeholder_loop.py`）把「启动时提交两个基线」当作既定行为。

### 诉求

- 运行启动与迭代过程中不提交任何测试集评测；测试集只在全部轮次终态后的终评环节出现。
- 终评环节同时提交两项测试集评测：初始版本（`base_commit`）的测试集基线，以及最终迭代后的 skill（最后一个已接纳轮的 commit）的测试集终评；没有接纳轮时**不回退** `base_commit`，而是新增一个记录本次运行结果的 commit 作为终评对象。
- 无接纳轮的结果 commit 记录 run 的终态结论（verdict、初始与终评分、指标与各轮决策），带 `Harness-Run-Id` 与明确的无接纳 verdict trailer；它不改变被进化的 skill 文件，可以是空提交或只新增 `.harness-evolution/` 下的结果文件。
- 两项测试集评测可以并行在途；两者都完成后才写 `evolution_finals`，`init_score`、`best_score` 与 `verdict` 的语义保持不变。
- 旧 run 或重试场景：已经完成的测试集基线直接复用，不重复提交；缺失时在终评环节补交。

## 目标

- 把 `test_baseline` 的提交从 `evolution_advance` 移到 `evolution_finalize`，让测试集在迭代结束前不被启动。
- 终评环节统一编排测试集基线与测试集终评，等待两者完成后再写终评行。
- 保持验证集基线、逐轮门控以及 `init_score`、`best_score`、`verdict` 口径不变。
- 启动路径不再因为测试集基线失败而阻塞第 1 轮；测试集相关失败与重试只发生在终评阶段。
- 事件、步骤状态与测试覆盖能清楚区分「迭代中只有验证集」和「终评阶段两次测试集评测」。

## 设计依据

- [07 §5.8 应用评测结果、重试与终评](../../../plans/fullstack-design/07-backend-implementation.md)：现有运行级评测、终评与重试路径；本 issue 调整测试集基线的提交时机。
- [14 §2 术语与语义](../../../plans/fullstack-design/14-target-project-ids.md)：验证集用于逐轮候选决策，测试集用于最终独立验收；本 issue 让测试集只在最终验收阶段出现。
- [Agent Note：SkillOpt 式基线门控与测试集终评](../../../.agents/notes/implemented/architecture/2026-11-25-baseline-gate-test-final.md)：记录「启动时并行提交两个基线」的现状与理由；本 issue 改变其中的测试集基线时机，需同步修订该 Note 及英文侧。
- [microsoft/SkillOpt](https://github.com/microsoft/SkillOpt)：最终在留出测试集上比较初始与最终版本；本 issue 不改变比较对象，只把两次评测移到迭代结束后。
- [05 §4.11 进化对象配置](../../../plans/fullstack-design/05-api-design.md) 与 [06 §5.2 evolution_runs](../../../plans/fullstack-design/06-database-design.md)：测试集模板 ID 的配置与快照；本 issue 不新增字段。

## 实现内容

### 方案总览

```text
run start / advance
  └─ validation_baseline only (base_commit)
turns ...
finalize (all turns terminal)
  ├─ test_baseline (base_commit)      ─┐
  └─ test_final   (accepted / result commit)    ─┴─ wait both → evolution_finals
```

- `EvolutionEvalSubmitter`：
  - 启动入口只提交验证集基线（如 `submit_validation_baseline`），不再提交 `test_baseline`。
  - 新增终评入口（如 `submit_test_evaluations`），一次提交 `test_baseline` 与 `test_final`，复用 `ensure_run_evaluation` 的幂等逻辑。
- `EvolutionAdvanceService.handle`：只提交验证集基线，不再触发 `test_baseline`。
- `EvolutionFinalizeService.handle`：所有轮次终态后先确保验证集基线（旧 run 兼容）；有已接纳轮时 `test_final` 使用最后一个已接纳 commit，没有已接纳轮时先新建并推送结果 commit（见下），再提交测试集基线与 `test_final`；任一未完成时返回未完成，不写 `evolution_finals`。
- 无接纳轮结果 commit：在 run 分支上生成一个记录运行终态的 commit（空提交或仅 `.harness-evolution/` 结果文件），消息含 `Harness-Run-Id`、`Harness-Verdict: no-acceptance` 与 verdict、分数、指标及各轮决策；它不修改 skill 文件，因此评测对象与 `base_commit` 不同；重试复用同一个 commit，不重复生成；该 commit 必须在提交 `test_final` 前可被平台读取（先推送 run 分支或该 commit）。
- `EvolutionEvalPoller`：
  - 终评 follow-up 的重新入队条件从只看 `test_final` 改为同时检查 `test_baseline` 与 `test_final`；两者都 completed 才入队 finalize。
  - 轮询路径继续按 `kind` 更新对应行；失败仍走 `blocked(stage=eval)`。
- `retry.py`：`/retry` 清理测试集基线或终评失败行时，按现有 `reset_run_eval_for_retry` 重新提交；已完成的基线不重置。
- 事件与前端：启动与迭代事件中不再出现测试集基线提交；终评步骤展示测试集基线与终评两条评测及最终对比。若前端仍只展示终评行，至少要让步骤状态等待两个评测完成，并用文案区分「测试集基线」与「测试集终评」。

### 兼容与边界

- 旧 run：如果 `test_baseline` 已存在且 completed，直接复用；缺失或 pending 时在终评补交。
- 已有 `test_final` 的旧 run：保持现有幂等行为，不重跑已完成的终评。
- 运行在终评前被取消或失败：不提交测试集评测。
- 测试集模板不可用或提交失败：在终评阶段进入 `blocked(stage=eval)`，错误信息区分 `test_baseline` 与 `test_final`；第 1 轮与已完成的迭代不受影响。
- 不改变 `validation_baseline` 的提交时机、门控逻辑与候选接纳规则。
- 不改变 `test_baseline` 的 commit 选择（`base_commit`）；`test_final` 有接纳轮时仍用最后一个已接纳 commit，无接纳轮时改用结果 commit，不再回退 `base_commit`。

## 实施步骤

1. 拆分提交入口：启动只提交验证集基线；新增终评阶段的测试集双评测提交。
2. 调整 `advance`、`finalize` 与 poller 的入队与等待条件，确保两个测试集评测都完成才写终评。
3. 实现无接纳轮的结果 commit：生成、幂等复用、先推送再提交 `test_final`；确认它不修改 skill 文件。
4. 更新 `retry` 与失败、事件文案；确认旧 run 与已完成评测的幂等复用。
5. 更新前端终评步骤的状态与文案（如需要），保持 `initScore` 与 `bestScore` 字段不变。
6. 同步修订设计文档、Agent Note 与测试：删除「启动并行提交测试集基线」与「无接纳回退 base_commit」的断言，新增「终评前不出现 testProjectId」「终评并行提交两条」「无接纳生成结果 commit 并作为终评对象」「两者完成才写 finals」的覆盖。

## 依赖与交付边界

- 依赖：PR #622 已合并的基线门控与运行级评测实现；`testProjectId` 配置与快照已存在。
- 不依赖 #620 的最终验收状态；本 issue 只改测试集评测时机。
- 交付边界：代码、测试、前端步骤状态、设计文档与 Agent Note；不改评测平台、模板或外部契约。
- 非目标：不取消测试集终评，不改变 verdict 规则，不改变初始与最终对比口径。

## 独立验证

```sh
pnpm test:api -- -k "baseline or finalize or run_evaluation"
pnpm verify:flow
pnpm lint:docs
pnpm verify:docs
```

- 数据：`bugfix-63-real-eval` 的运行级评测测试、`m5-11-evolution-recovery` 的完整占位循环、fake 与真实 gateway 桩。
- 预期：
  - 启动与迭代阶段没有任何 `testProjectId` 的提交；测试集模板的 launch 次数为 0。
  - 全部轮次终态后，终评阶段对 `base_commit` 与最终 commit 各提交一次测试集评测；有已接纳轮时最终 commit 是最后一个已接纳 commit，无接纳轮时是新增的结果 commit，两者可以并发在途。
  - 无接纳轮运行生成且只生成一个结果 commit，`test_final` 的对象是该 commit 而不是 `base_commit`；结果 commit 记录 verdict、分数、指标与各轮决策，且不修改 skill 文件；重试不重复生成。
  - 两者都 completed 后才写 `evolution_finals`；`init_score`、`best_score` 与 `verdict` 与现状一致。
  - 模拟测试集基线失败时运行进入 `blocked(stage=eval)`，第 1 轮与已验证轮次不受影响；`/retry` 只重提失败项。
  - 旧 run 已有 completed 的 `test_baseline` 时不重复提交。

## 验收标准

- 启动与迭代路径不再提交 `test_baseline`；测试集模板在终评前零调用。
- 终评环节同时存在 `test_baseline` 与 `test_final` 两条评测，commit 分别为 `base_commit` 与最终 commit（有接纳轮时为最后一个已接纳 commit，无接纳轮时为结果 commit）；两者完成后才写终评。
- `evolution_finals` 的 `init_score`、`best_score` 与 `verdict` 口径不变，前端终评步骤能区分两条评测。
- 旧 run、失败重试、无接纳轮（生成结果 commit，终评对象不等于 `base_commit`）三条路径均有测试覆盖。
- 相关测试、流程、文档与双语配对门禁通过。

## 门禁与 CI

- 命中：`pnpm test:api`、`pnpm test:gates`、`pnpm verify:flow`、`pnpm verify:flow-online`、`pnpm lint:docs`、`pnpm verify:docs`、`pnpm typecheck:api`、`pnpm lint:api`。
- 若前端改动：`pnpm test:web`、`pnpm typecheck:web`、`pnpm lint:web`、`pnpm verify:web-style`。
- 不新增门禁脚本。

## 非目标

- 不改变验证集基线与逐轮门控；不改变 `verdict` 的严格更优规则。
- 不取消测试集终评，也不把测试集改成只跑一次；初始与最终版本仍在测试集上各评一次。
- 不改评测平台契约、模板或服务令牌；不改对象配置字段。
- 不做无关的基线或终评 UI 重设计。
