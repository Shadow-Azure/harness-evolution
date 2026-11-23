# 自进化运行缺少中途暂停与继续：增加安全检查点和持久化控制

[English](bugfix-evolution-pause-resume.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-02
milestone: bugfix
depends:
  - m10-06
  - m5-11
priority: P2
status: done
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - docs/**
  - .agents/**
adr:
  - ../../notes/implemented/feature/2026-11-20-evolution-pause-resume.md
github:
  number: 436
  url: https://github.com/Shadow-Azure/harness-evolution/issues/436
```

## 背景

### 场景与前端复现

访问 http://8.149.232.63/，以 admin 登录，进入空间「自进化」→「正在执行」→运行详情。2026-11-20 前端只读核实：已有 systematic-debugging v6.4.1 运行显示「正在执行」、第 6/7 步「迭代优化」、第 1/1 轮、71%；列表和详情页均没有「暂停」「继续」或停止推进的控制。详情可查看七步、日志、目标与输入、工作区；用户只能等待任务结束或异常。复现用现有运行，未新增运行、未操作生产进程、未改变配置；生产截图与完整运行标识只保留本地，不入仓库。

当用户发现版本、时间范围选错，需要先检查归因/候选，或希望暂缓后续模型、Git 推送与评测开销时，无法让运行在可恢复位置停下。关闭页面只结束浏览，不会停止服务端；重启进程属于异常中断，会影响其他任务，不能作为暂停方式。此项是运行控制能力缺口，不把当前运行停在某一步直接判为执行卡死。

### 当前流程与分析结论

四步向导先做范围、Session、潜在 bad case、归因预览；正式启动持久化对象/ref/digest、策略、空间、时间及评测配置。后台 prepare 执行范围确认、关联 Session、潜在匹配、归因、聚类，并准备 Git 工作区和轮次；页面前五步主要属于同一个 prepare job。之后 advance 针对一个问题簇生成 patch、提交并推送候选、提交外部评测；独立 poller 收集结果，apply 按外部 verdict 接纳/拒绝，调度下一轮；最后 finalize 汇总及发布。终评目前包含汇总/占位逻辑，本 issue 不承诺兑现真实终评。

现有 progress_unit、round 状态、候选 commit、外部评测 ID、事件和幂等认领可作为继续执行的基础。推荐「安全检查点协作式暂停」，难度中等；不是冻结 Python 协程、模型 token、Git 子进程或外部评测。仅每轮末尾暂停过粗，用户可能等完整评测；强杀式立即停止容易留下半成品和未知外部副作用，不作为首版方案。

### 根因与代码入口

- 领域状态只包含 preparing/running/blocked/completed/failed/interrupted；没有用户暂停意图、确认暂停状态及恢复阶段，见 apps/api/app/service/evolution/state.py、db/models/evolution.py。
- API 与前端只提供 blocked 的 retry；retry.py 拒绝非 blocked 的运行（409 RUN_NOT_RETRYABLE）。RunDetail.vue 对 interrupted 只显示中断及日志；异常恢复与主动暂停语义不同。
- prepare.py 按 progress_unit 跳过已完成部分，但一个 job 内连续执行多个步骤，没有暂停检查点；mark_prepared 等写入还可能覆盖并发控制状态。
- advance.py 的 EvolutionJobLifecycle 在 job 完成后继续投递；eval_poller.py 也会独立补调度 advance/apply/finalize；blocked_sweeper.py 会投递自动重试。只在按钮或某一个入口检查状态会漏掉推进路径。
- jobs.py 用全局 worker_lock 串行执行；暂停时若在 handler 内等待继续，会占住 worker，阻塞其他运行和同步。CancelledError 当前被映射为 interrupted，不是可恢复暂停。
- 工作区保留当前只保护 preparing/running/blocked。新增暂停后若不扩展保留集合，清理器可能删除暂停任务的 Git 工作区。
- 外部评测网关现有 submit/get_status/get_result，没有统一 pause/resume/cancel；eval_poller.py 用 eval_started_at 计算墙钟超时。停止本地推进不等于外部任务停算，暂停时间也不能直接触发恢复后误判超时。

## 目标

- preparing/running 运行可请求暂停，显示「正在暂停」；到达当前安全操作边界后确认「已暂停」，保留全部产物和原运行身份。
- 已暂停运行可继续，准确接续下一项未完成工作；不重跑完成阶段、不重复提交候选或评测。
- 暂停状态跨刷新、API 重启保持；其他任务继续执行。blocked 的重试、failed/interrupted 的异常语义保持独立。
- 页面清楚说明暂停生效边界和外部评测仍可能运行，不承诺立即停止开销。

## 设计依据

- [07 §5.11 七步与 prepare 管线](../../../plans/fullstack-design/07-backend-implementation.md#511-v2-流程重排七步与-prepare-管线) 与 [§6.1 串行执行器](../../../plans/fullstack-design/07-backend-implementation.md#61-串行执行器v1)：执行编排、持久化游标与 worker 边界。
- [08 §10.2 运行详情交互](../../../plans/fullstack-design/08-frontend-implementation.md#102-交互)：详情动作、事件及状态展示。
- [05 API 设计](../../../plans/fullstack-design/05-api-design.md) 与 [06 数据库设计](../../../plans/fullstack-design/06-database-design.md)：空间鉴权、接口及迁移的宿主；现有设计没有暂停契约，实施时须在这些章节补齐，不能声称暂停已由旧设计定义。
- 方案理由见 Agent Note 的 proposed/feature/2026-11-20-evolution-pause-resume；本文方案为待实现建议。

## 实现内容

### 持久化控制与 API

新增独立于执行阶段的控制状态 running/pause_requested/paused（可等价建模），保存请求人/时间、确认暂停时间及恢复所需执行位置；不要把 blocked 当作人为暂停。状态、job/round 认领与恢复投递采用事务/条件更新，解决暂停和完成、暂停和入队、重复继续的竞争。终态优先；仅 preparing/running 可请求暂停，paused 才能继续，blocked 继续使用 retry；终态及非法转换返回明确 409，重复请求幂等。按空间管理权限提供 POST /api/workspaces/{wid}/evolution/runs/{runId}/pause 与 /resume（拟议），返回服务端真实控制状态和动作可用性。用户暂停后直到显式继续前不得被 sweeper 自动推进。

### 检查点与恢复

prepare 在关联、潜在、归因批次、聚类、工作区准备等持久化边界检查控制意图；耗时操作可完成当前不可分割单元，完成后保存再让出。迭代在 patch 产物保存、候选提交、推送、评测提交、apply 和 finalize 的安全边界设置检查点；明确每个中间态如何续接，不能只检查 progress_unit。暂停应正常退出 handler、释放 worker，不占锁等待；任务完成回调不得因此误投后续阶段。已入队任务执行前重新检查，未开始工作不产生新副作用；不能丢弃唯一待续任务而让 resume 无法重投。

继续按数据库中的阶段/round/commit/externalId 重建下一项工作，在同一 run 下至多创建一个有效 job；已有 patch/commit/push/外部评测不得重复提交。推送响应未知等不确定副作用先核实远端并幂等重试，不能假定没有成功。恢复沿用冻结的版本/正文 digest/基线，移动分支不能改写本次输入。暂停中刷新、部署/重启不得进入 interrupted 或自动恢复；保留原始 blocked 原因。

### 外部评测与生命周期

首版仅暂停本系统推进：已提交外部评测可继续，观察器可读取并持久化结果，但不得 apply、推进下一轮或 finalize；继续复用 externalId。提交后请求未响应时也须避免恢复时重复提交。区分外部评测失败与本地观察窗口过期；暂停时间不计入本地未观察等待超时，恢复先核实已有任务状态，不能因暂停时长直接判 timeout。将 pause_requested/paused 纳入工作区和候选产物保留策略，恢复后再按终态正常回收。

### 前端与契约

列表和详情在可操作状态显示暂停/继续；正在暂停明确当前尚未完成的操作，已暂停显示时间和继续入口，刷新与 SSE 断线重连后仍取服务端状态。展示「当前操作完成后暂停；已提交外部评测可能继续运行」；paused 是活跃保留态，不能掉进失败历史或丢失。增加 pause_requested/run_paused/run_resumed 等可区分用户操作与异常重试的事件及操作者；事件名可等价实现。先改 FastAPI 模型后生成 OpenAPI/TS，禁止手改生成文件；同步设计文档、双语、状态映射与测试。

## 实施步骤

1. 补数据/状态转换设计与合成失败用例，明确执行阶段和控制状态的组合、动作权限、检查点及不可分割操作。
2. 增加双方言迁移、repository 条件更新、暂停/继续 API 与事件，覆盖重复请求、越权和终态竞争。
3. 接入 prepare/advance/apply/finalize、job 回调、评测 poller、blocked sweeper 与工作区保留；补齐中间产物恢复和重启恢复。
4. 更新列表、详情和 SSE 反馈，生成契约并同步设计与双语文档。
5. 用可控的合成 Git/模型/评测适配器做跨栈回归和前端 Before/After，不在生产测试强杀或重复评测。

## 依赖与交付边界

依赖 m10-06（运行详情）和 m5-11（异常恢复），按 P2 功能增强交付。本 issue 在关联 PR 内实现持久化暂停与继续、跨栈回归和原型对照；生产运行不作为测试对象。恢复必须复用冻结输入；历史输入无法证明时明确诊断，不猜测版本或重新匹配。

## 独立验证

```sh
pnpm contract:generate
pnpm contract:check
pnpm typecheck:api
pnpm typecheck:web
pnpm lint:api
pnpm lint:web
pnpm test:api
pnpm test:db
pnpm test:db:mysql
pnpm test:web
pnpm test:integration
pnpm test:e2e -- --pattern evolution-pause
pnpm verify:flow
pnpm verify:docs
```

新增 evolution-pause E2E；用 fake engine/gateway 和临时 Git 仓库控制 prepare、patch、push、evaluating、apply/finalize 各阶段。每次记录 runId、progress_unit、round 状态、candidate commit、externalId、提交次数和worker是否释放。先断言暂停成功再推进 fake 完成事件，验证没有新副作用；继续后完成同一 run。断线、重启、重复点击、另一运行并行提交、推送响应未知及暂停跨评测超时均要覆盖。需要等待状态时使用带截止时间的脚本内轮询，不以多次人工命令加 sleep 验证。以上为实施阶段命令，本 issue 发布不声称已通过未来功能测试。

## 验收标准

- 有权限用户能从列表/详情暂停 preparing/running 运行；显示请求已受理与真正暂停两种状态，数据可信，未承诺即时中止当前原子操作。
- 暂停确认后不再开始 patch、commit/push、评测提交、apply 或下一轮；外部评测只允许收集结果。
- 继续沿用同一运行和冻结输入，已完成产物不重做；重复调用仅一次有效恢复。
- 暂停跨刷新、服务重启及工作区清理仍可恢复；其他任务不被暂停任务占锁。
- paused 不被 sweeper 重试，不丢 blocked 信息；终态、越权、并发完成行为确定且可测试。
- 长暂停恢复时先核实外部任务，不重复提交且不因本地暂停时长误报超时。
- 迁移、共享契约、SSE、状态筛选、详情与列表一致；合成跨栈和常见视口验证通过，不含生产数据。

## 门禁与 CI

CI 必须执行聚焦状态机/恢复测试、双方言 DB、前后端单测及新增 E2E；覆盖率不低于 80%。运行 contract/typecheck/lint、verify:flow 与文档双语门禁。提交和 PR 标题带本 issue 编号；截图/日志不含生产 Session 内容和凭据，不直接改生成契约。

## 非目标

- 不做立即强杀、模型 token 级续写、Git 命令内部冻结或外部评测平台 pause/cancel API。
- 不把暂停实现成 blocked/interrupted，不通过重启服务暂停，不回滚已完成推送。
- 不允许暂停期间修改运行的版本、策略或输入；改条件应创建新运行。
- 不顺手兑现真实 patch/终评、改归因算法、修复运行详情其他布局问题或重构全局调度器。
