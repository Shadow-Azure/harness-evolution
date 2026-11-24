# 部署重启后中断的自进化 job 不会自动续跑：启动恢复漏掉 interrupted 行

[English](bugfix-shutdown-interrupted-job-recovery.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-49
milestone: bugfix
depends:
  - bugfix-11
priority: P2
status: in-progress
scope:
  - apps/api/**
  - tests/**
  - docs/**
  - .agents/**
adr: []
github:
  number: 578
  url: https://github.com/Shadow-Azure/harness-evolution/issues/578
```

## 背景

### 事故与现象

2026-11-24 14:39（+08），生产 run `01M864EY6A9JHK3HKE48EP07T0`（target `skill:codespec-subagent-driven-development@openspec-cn-main-copy-ar-a7ec200-claude-core`，空间 `OpenSpec-cn_SWE-bench`）在 prepare 阶段启动。14:49:51，运行详情页显示「任务被中断，系统将自动恢复；可查看最后事件 job interrupted during shutdown」，状态为「已中断」。15:15 复查仍是 `interrupted`，没有恢复事件、没有新 job，页面也没有重试入口。

- run：`status=interrupted`、`controlState=running`、进度 50%（3/6）、阶段文案「第 4/7 步 · 对象归因中…」；`error={stage: prepare, message: job interrupted during shutdown, at: 2026-11-24T14:49:51+08:00}`。
- run 事件只有 5 条：14:39:00 创建、prepare 启动、Session 关联 22/166、潜在 bad case 22 个；14:49:51 记录 `run_interrupted`（`job interrupted during shutdown`，job `01M864EY6AQFE0BTRP50RMEPK7`）。没有 `workspace_prepared`、`clusters_created`，也没有任何 `job_recovered` 或「进程重启后已自动重新排队」。
- prepare job：`status=interrupted`、`error=job cancelled during shutdown`、14:39:00 开始、14:49:51 结束。
- 归因批次 job：`01M864EYBQHMZ5E4J8MSA3SSCD`（`attribution_batch`）同样 `status=interrupted`，进度 9/22（40.9%），记录 6 个失败，平均单例约 262 秒、p95 约 312 秒；14:49:51 结束。
- 部署侧：Deploy run `45343097443` 发布 `933b143a`，release 日志在 14:49:26 执行 `systemctl restart harness-api`，14:49:51 进入健康检查；run 的中断时间与默认 25 秒 drain 窗口的结束点同秒。

### 根因分析过程与结论

1. 从生产页面及其认证 API 读取 run、事件、prepare job 与 attribution job，确认这不是业务失败：run 和两个 job 都是 `interrupted`，错误文案都来自停机路径，归因批次当时仍在推进（9/22）。
2. 对齐 Deploy run `45343097443` 的 release 日志：14:49:26 重启 `harness-api`，14:49:51 健康检查；run 的 `error.at` 与重启排水结束点精确到秒重合，确认中断由发布重启触发。
3. 读停机路径 `JobRunner.close()` / `_drain_and_cancel()`：SIGTERM 后最多等待 `HE_JOB_DRAIN_TIMEOUT_SECONDS`（默认 25 秒），超时取消在跑 handler；`_run()` 的 `CancelledError` 分支调用 `JobRepository.interrupt()`，把 job 从 `running` 写成终止态 `interrupted`，并记录 `run_interrupted`。
4. 读启动恢复 `JobRunner.recover()`：先 `requeue_running_kind("attribution_batch")`，再 `mark_running_interrupted("process restarted")`；两者都只匹配 `status=running`。这次重启发生在旧进程已把行写成 `interrupted` 之后，因此这两个查询都看不到它们，`_requeue_interrupted()` 不会执行，也不会写 recovery 事件或新 job。
5. 读前端与重试入口：`RunDetail.vue` 对 `interrupted` 只显示「系统将自动恢复」；`/runs/{id}/retry` 只接受 `blocked`，`retry.py` 拒绝其他状态。因此页面的恢复承诺没有后端实现，run 只能人工介入。

**结论**：本次中断的直接触发是 14:49:26 的生产发布重启；根因是停机与启动恢复的状态契约断裂。优雅停机把在跑 job 写成终止态 `interrupted`，而启动恢复只接管仍为 `running` 的行，`interrupted` 行没有任何重排路径。结果是所有跨发布的 `evolution_prepare` 以及它等待的 `attribution_batch` 都会永久停在中断态，与页面「系统将自动恢复」的承诺相反。这是 #474 验收标准「停机 drain 超时后 job 安全释放并由恢复流程接管」尚未兑现的剩余缺口；#474 的测试覆盖了「进程崩溃后 job 仍为 running」的恢复，没有覆盖「优雅停机已写 interrupted」的恢复。

**限制**：没有 SSH 进入生产机读取 `journalctl`；结论基于 run/job 的持久状态、事件时间线、Deploy run 日志和停机/恢复代码路径。未重跑该 run，也未修改生产数据。

## 目标

- 唯一推荐方案：让启动恢复接管优雅停机写入的 `interrupted` job，而不是只接管 `running` 行。重启后自动把中断的 evolution job 与 attribution batch 重新入队，run 从既有检查点继续，不需要人工 retry，也不重复已完成的归因。
- 具体语义：
  - `attribution_batch`：把因停机中断的行重新置为 `queued`，保留批次身份、进度和已完成结果；父 prepare 恢复后 join 同一批次。
  - `evolution_prepare` / `advance` / `apply` / `finalize` / `retry`：按 `(kind, ref_id)` 只恢复最新的中断 job，经 `EvolutionControlRepository` 的运行态、暂停和 blocked 栅栏重新入队；已完成或 blocked 的 run 不恢复。
  - 记录 `job_recovered` 事件并调用 `start_queued()` 调度；保留原始 `run_interrupted` 事件，不覆盖。
  - 幂等：同一 job 恢复后不再是 `interrupted`，第二次重启不会重复入队；`pause_requested` / `paused` 的 run 不自动恢复。
- 该方案直接修复根因（终止态缺少恢复路径），不依赖延长 drain、冻结发布窗口或人工点击重试。

## 设计依据

- [07 §5.8.1 阻塞重试策略](../../../plans/fullstack-design/07-backend-implementation.md#581-阻塞重试策略)：现有 blocked/retry 语义；本 issue 只补 `interrupted` 的恢复，不改变 blocked。
- [07 §5.6 单轮执行](../../../plans/fullstack-design/07-backend-implementation.md#56-单轮执行candidate--push--提交评测fullevolutionengineadvance_one_round)：阶段边界与检查点，恢复从已持久化阶段继续。
- [06 §3.9 job_runs](../../../plans/fullstack-design/06-database-design.md#39-job_runs--统一任务表)：job 状态机与 lease 字段；本 issue 需要按 `status=interrupted` 查询可恢复行。
- [06 §5.7 evolution_run_events](../../../plans/fullstack-design/06-database-design.md#57-evolution_run_events--执行过程与异常追加)：`run_interrupted` / `job_recovered` 的事件口径。
- [04 §3 分层与目录](../../../plans/fullstack-design/04-backend-architecture.md#3-分层与目录)：恢复编排留在 service，状态查询留在 db。
- #474（bugfix-11）：租约、心跳、drain 与启动恢复的既有实现；本 issue 修复其未覆盖的 graceful-shutdown 分支。
- 停机配置：`deploy/harness-api.service` 的 `KillMode=mixed` + `TimeoutStopSec=45`，以及 `docs/deployment.md` 的重启排水说明。

## 实现内容

1. 查询与状态：在 `JobRepository` 增加「最近一次停机中断」查询，筛选 `status=interrupted`、`kind` 在可恢复集合、`attempt < max_attempts`、`cancel_requested=false`，按 `(kind, ref_id)` 取最新一行；只选择 run 仍为活动状态且 `control_state=running` 的行。
2. 启动恢复：`JobRunner.recover()` 在现有 `mark_running_interrupted()` 之后增加对上述行的恢复：
   - `attribution_batch`：复用 `requeue_running_kind` 的复位语义（`status→queued`、清 lease/error），但匹配 `interrupted` 行；避免重新执行已完成的 case。
   - evolution job：调用 `EvolutionControlRepository.requeue_interrupted` 的同一栅栏重新入队；`control_state != running`、`status` 为 `completed` / `failed` / `blocked`、已有活跃 job、或 `resumed_at >= finished_at` 时跳过。
   - 记录 `_record_recovery()`；不要对已经是 `interrupted` 的行再写一条 "process restarted" 的 interruption，避免重复事件。
3. 调度与顺序：恢复只入队不执行，最后走 `start_queued()`；attribution batch 先于父 prepare 入队，保证 `run_for_prepare` 能 join 到同一批次。
4. 可观测性：recovery 事件包含 `previousJobId`、`jobId`、`stage`；启动日志汇总恢复行数、kind 与 run；不记录 Session 内容或凭据。
5. 测试：新增 `apps/api/tests/bugfix-49-shutdown-recovery/`，覆盖停机后重启、幂等、栅栏和 9/22 批次续跑。
6. 文档：把 `docs/deployment.md` / `docs/deployment.en.md` 的重启排水说明改成与实现一致；若事件类型需要新增，按 06 §5.7 先改契约。

## 实施步骤

1. 补 job 查询与单测：按 kind/ref/status 取最新停机中断行，并验证历史行不会被再次选中。
2. 改 `recover()`：接管 `interrupted` 行，attribution batch 与 evolution job 分别入队，记录 recovery 事件。
3. 接 control 栅栏：排除 pause/blocked/active job，保证同一 run 同一 kind 只有一个 replacement。
4. 加回归测试：close→recover、连续两次 recover、pause/blocked run、9/22 续跑。
5. 跑门禁并更新 deployment 文档；在本 issue 下记录验证结果。

## 依赖与交付边界

- 依赖：bugfix-11（#474）已交付的 lease/heartbeat/drain 与 `_INTERRUPTIBLE_KINDS`；m5-11 的进程恢复与事件语义。
- 交付边界：只修启动恢复对 `interrupted` 行的接管；不改七步算法、归因执行器、Git 幂等、部署流程和 UI 状态文案；不引入外部编排或多实例 leader election。
- 不把真实 blocked/失败自动恢复成成功；只恢复停机中断。

## 独立验证

```sh
pnpm test:api -- tests/bugfix-49-shutdown-recovery
pnpm test:api -- tests/bugfix-11-durable-jobs
pnpm test:api -- tests/m5-11-evolution-recovery
pnpm test:db
pnpm typecheck:api
pnpm verify:flow
pnpm test:gates
```

- 模拟 drain 超时：prepare 与 attribution_batch 均为 `interrupted`；重启恢复后两 job 均变为 `queued`，prepare 从 `progress_unit=3` 继续，attribution 只补未完成 case，run 不再停在 `interrupted`。
- 连续两次恢复只入队一次；pause/blocked run 不被恢复。
- 生产等价场景（22 个 case、9 个完成）恢复后完成数只增不减，不重复调用已完成 case。

## 验收标准

- 优雅停机（部署或 `kill -TERM`）把在跑 job 标 `interrupted` 后，下一次启动无需人工操作即重新入队并继续；run 事件出现 `job_recovered`，最终状态不再是永久 `interrupted`。
- `attribution_batch` 与父 `evolution_prepare` 都能恢复；恢复不重复已完成的归因结果。
- pause/blocked/completed 的 run 不被自动恢复；第二次重启不产生重复 job。
- 生产同构测试覆盖 9/22 的批次边界；文档与事件口径一致。

## 门禁与 CI

- `pnpm test:api`、`pnpm test:db`、`pnpm typecheck:api`、`pnpm verify:flow`、`pnpm test:gates`；涉及文档时运行 `pnpm lint:docs`。
- 新增的 restart/resume 测试必须进入 CI；不写生产日志、Session 内容或凭据。

## 非目标

- 不通过延长 drain 超时或冻结发布窗口规避问题，也不依赖人工 retry。
- 不改变 blocked 与真实失败的重试语义。
- 不改七步引擎算法、归因 Skill、Git push 幂等或 UI 设计。
- 不做多实例 leader election 或外部工作流引擎。
