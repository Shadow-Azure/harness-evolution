# 自进化评测超时按提交时刻计费且不分评测类型，排队与大测试集导致误超时

[English](bugfix-eval-timeout-queue-and-kind.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-72
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - apps/api/app/service/evolution/**
  - apps/api/app/third_party_api/**
  - apps/api/app/config.py
  - apps/api/app/main.py
  - apps/api/tests/**
  - .env.example
  - .agents/notes/**
  - .agents/flow/issues/**
  - plans/**
adr: []
github:
  number: 659
  url: https://github.com/Shadow-Azure/harness-evolution/issues/659
```

## 背景

### 现象

生产自进化 run [`01M8DEKFZ5R70HARCQZW562BGR`](http://8.149.232.63/workspaces/01M7KJ05ENF9784GPBDV544VB0/evolution/runs/01M8DEKFZ5R70HARCQZW562BGR)（对象 `codespec-subagent-driven-development`，基线 `59bebcfe`，2026-11-27 10:50 创建）在第 6/7 步「迭代优化」被阻塞，运行详情显示：

- `status=blocked`、`blockedStage=eval`、`error.stage=eval`、`error.message="evaluation timed out"`；
- 终态时间 `2026-11-27T12:55:42+08:00`；
- 超时事件 `eval_timeout` 的 payload 是 `{"kind":"test_baseline","externalId":"78369938-bdb3-45bb-9c1e-deed8fdfbf84","status":"timeout"}`，不是第 1 轮候选评测。

同一次运行的评测时间线（`GET /api/workspaces/{wid}/evolution/runs/{rid}/events` 的原始事件）：

| 时间（+08:00） | 事件 | 关键字段 |
|---|---|---|
| 10:54:38 | 提交验证集基线 | `291187d7-30fd-4893-b98b-967813e6439f` |
| 10:54:40 | 提交测试集基线 | `78369938-bdb3-45bb-9c1e-deed8fdfbf84`，`kind=test_baseline` |
| 11:11:34 | 提交第 1 轮候选评测 | `87aa26d2-21e7-45c7-9e14-39422a663b6a` |
| 11:55:08 | 验证集基线完成 | 从提交到完成约 60 分 30 秒 |
| 11:16:34–12:46:42 | 候选评测持续 `queued` | 每 5 分钟轮询一次；12:52:12 首次 `running`，距提交 100 分 38 秒 |
| 12:50:42 | 测试集基线仍 `running` | 已提交约 1 小时 56 分 |
| 12:52:12 | 候选评测首次变为 `running` | 距提交 100 分 38 秒 |
| 12:55:42 | 测试集基线超时，整 run 阻塞 | 距测试集基线提交 2 小时 1 分 2 秒；候选评测此时只实际运行了约 3 分 30 秒 |

也就是说：真正被判定超时的是**测试集基线**，候选评测在它死亡时刚刚开始运行；run 被阻塞并不是因为候选评测本身失败或超时。

### 定位过程

1. 用管理员账号登录生产 API，读取 run 详情与全部 76 条事件，确认 `eval_timeout` 的 `kind` 是 `test_baseline`，候选评测的 `roundId=01M8DET5GNQY8YG1AXEQSM2K2R` 在 12:52:12 仍为 `running`。
2. 对照事件时间与代码中的时间字段：`EvolutionEvalSubmitter` 在提交时把 `started_at=now` 写入 `evolution_rounds.eval_started_at` / `evolution_evaluations.eval_started_at`；`EvolutionEvalPoller._expire_if_due` 与 `_expire_run_if_due` 都用 `now - eval_started_at` 与固定 `timeout` 比较。因此 2 小时从**提交时刻**开始计，而不是从平台真正开始执行计。
3. 对照 `ai-eval-platform` 的 `/api/v1/eval-runs/{id}/status` 契约：状态响应包含 `status`、`progress`、`started_at`、`duration_seconds`；`preparing`/`queued` 映射到 HE 的 `queued`，`running`/`finalizing` 映射到 `running`。HE 的 `AiEvalPlatformGateway.get_status` 目前只保留 `status`，把 `started_at` 和 `progress` 全部丢弃，轮询侧无法区分「排队等待」与「真正执行」。
4. 对照平台容量实现（[`capacity.py`](https://github.com/Shadow-Azure/ai-eval-platform/blob/main/backend/app/services/capacity.py) 与 [`dispatcher.py`](https://github.com/Shadow-Azure/ai-eval-platform/blob/main/backend/app/services/dispatcher.py)）：同一资源池上，后提交的评测只能使用 `pool_max - 其他 run 在途 attempt` 的容量。本 run 在启动时同时提交了验证集基线、测试集基线和候选评测，候选评测的 `queued` 区间（11:16–12:46）与测试集基线的 `running` 区间完全重合；在平台的跨 run 容量预留下，先启动的测试集基线会占住候选所需的槽位，这是候选排队 100 分钟最直接的容量来源。该调度问题已由 #656「测试集基线与最终评测统一在终评环节执行」单独跟踪，本 issue 不重复处理。
5. 复核其它运行：2026-11-26 的两个真实平台 run（`01M8AJ3WS9D5H16F2WHV5A1K74`、`01M8BTSPJA3XBB8WY2T5B7219E`）同样在启动阶段提交两项基线，候选评测也长期 `queued`，说明这不是单次偶发。

### 根因

1. **超时从提交时刻计费，排队时间被当成执行时间。** 候选评测 11:11:34 提交、12:52:12 才开始 `running`，2 小时预算已被排队消耗 100 分钟；即使没有测试集基线抢先超时，它也会在 13:11:34 被判超时，而实际只执行约 19 分钟。这是 `_expire_if_due` / `_expire_run_if_due` 直接使用 `eval_started_at` 的结果，与平台是否已经开始执行无关。
2. **所有评测类型共用同一个 2 小时硬上限。** `HE_EVAL_TIMEOUT_SECONDS` 默认 7200，验证集基线、逐轮候选、测试集基线、测试集终评完全一样。测试集是留出集，其用例规模和单例预算不能假定与验证集 mini-set 相同；平台侧的 `case_timeout_seconds` 默认 3600、`max_attempts` 默认 2，并且按资源池容量分片执行，2 小时不可能覆盖一次完整测试集评测。本 run 的测试集基线在 2 小时处仍在 `running`，就是该预算与评测规模不匹配的直接证据。
3. **超时诊断信息不足，掩盖了上述区分。** `EvalStatus` 只有 `status` 和可选的 `message`，`eval_polled` 事件只记录平台状态字符串，没有 `startedAt` 或完成百分比；运维只能看到最终一句 `evaluation timed out`，无法判断是平台排队、执行慢，还是真的卡死。

## 目标

- 评测超时只计量平台真正执行的时间：`queued`/`preparing` 不消耗执行预算，进入 `running` 后才开始计时。
- 按评测类型设置预算：验证集基线与逐轮候选沿用 2 小时执行上限；测试集基线与测试集终评使用更大的、可配置的执行上限。
- 仍能发现真正卡死的评测：排队和执行各有一条可观测的兜底上限，超时时事件里能看出卡在哪个阶段、已等待/执行多久。
- 不改变评测门控与终评语义：候选仍须严格优于基线，测试集终评仍以测试集基线为 `init_score`。

## 设计依据

- [07 §5.7 评测接入与轮询](../../../plans/fullstack-design/07-backend-implementation.md)：现有 `HE_EVAL_TIMEOUT_SECONDS`、5 分钟轮询与 `failed/timeout → blocked` 路径；本 issue 把「提交即计时」改为「执行才计时」，并按 kind 分档。
- [04 §9 配置项清单](../../../plans/fullstack-design/04-backend-architecture.md)：`HE_EVAL_POLL_SECONDS=300`、`HE_EVAL_TIMEOUT_SECONDS=7200` 的定义位置；本 issue 新增测试集预算与排队预算两个配置项。
- [Agent Note：SkillOpt 式基线门控与测试集终评](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/architecture/2026-11-25-baseline-gate-test-final.md)：运行级评测、测试集基线与终评的既有语义；本 issue 只改超时计量，不改比较对象。
- [#656 测试集基线与最终评测统一在终评环节执行](https://github.com/Shadow-Azure/harness-evolution/issues/656)：消除测试集基线对候选评测的容量抢占；本 issue 与其正交，但必须同时落地，否则终评阶段的两项测试集评测仍会在 2 小时处被误杀。
- 平台状态契约：`GET /api/v1/eval-runs/{id}/status` 返回 `started_at`、`progress`、`duration_seconds`（[`results.py`](https://github.com/Shadow-Azure/ai-eval-platform/blob/main/backend/app/api/results.py)）；这为「执行开始时间」提供了权威来源，无需新增 HE 数据库列。

## 实现内容

### 1. 让网关暴露执行开始时间与进度

- `service/evolution/engine/contracts.py` 的 `EvalStatus` 增加可选字段：`started_at: datetime | None` 与 `progress_percent: float | None`（后者用于观测，允许为空）。
- `third_party_api/eval_gateway/ai_eval_platform.py` 的 `get_status` 解析平台响应中的 `started_at`（ISO-8601，带时区）、`progress.percent`，解析失败时字段为 `None`，不改变状态判定。
- `third_party_api/eval_gateway/fake.py` 支持在测试中返回 `started_at`，便于构造「先排队、后执行」的场景。

### 2. 超时改为按执行时间计费，并区分排队

- `service/evolution/eval_poller.py` 的 `_expire_if_due` 与 `_expire_run_if_due`：
  - 当平台状态是 `running` 时，执行起点取 `status.started_at`；平台未返回时回退到 `eval_started_at`（兼容旧平台，行为与今天一致）。
  - 当平台状态是 `queued` 时，不检查执行超时；改用排队上限 `HE_EVAL_QUEUE_TIMEOUT_SECONDS`（默认 21600 秒，6 小时）与 `eval_started_at` 比较，防止平台永久排队导致 run 永远悬空。
  - 超时事件 payload 增加 `startedAt`、`elapsedSeconds`、`queueSeconds`、`progressPercent`，`eval_polled` 事件同样带上，便于区分排队与执行。
- 队列上限只作为安全网，不参与正常评测的执行预算；真正卡死的判定仍由测试集/候选各自的执行预算负责。

### 3. 按评测类型分档预算

- `config.py` 增加 `eval_queue_timeout_seconds` 与 `eval_test_timeout_seconds`：
  - `HE_EVAL_TIMEOUT_SECONDS`（默认 7200）：验证集基线与逐轮候选的执行上限，保持现状。
  - `HE_EVAL_TEST_TIMEOUT_SECONDS`（默认 21600）：测试集基线与测试集终评的执行上限；测试集用例数、平台分片与重试都更长，6 小时是首版保守值，可按实际平台吞吐调整。
  - `HE_EVAL_QUEUE_TIMEOUT_SECONDS`（默认 21600）：任何评测从提交起的最长排队时间。
- `main.py` 构造 `EvolutionEvalPoller` 时把三个值传入；`eval_poller` 按评测 kind 选择预算：`run_evaluation.kind in {"test_baseline","test_final"}` 用测试集预算，轮次候选与 `validation_baseline` 用候选预算。
- `.env.example` 补三项注释与默认值；`plans/fullstack-design/04-backend-architecture.md` 的配置表同步，避免文档与代码漂移。

### 4. 测试覆盖

- 在 `apps/api/tests/m12-03-real-patch-eval/test_eval_poll_transient.py` 增加「排队 3 小时后开始执行、执行 30 分钟」的用例，断言不产生 `eval_timeout`，且 `eval_started_at` 不被改写。
- 增加「候选排队 100 分钟 + 执行 2 小时零 1 分」用例，断言只在执行满 2 小时后超时，而不是按提交时间提前触发。
- 增加「测试集基线执行 2.5 小时」用例，断言在 6 小时测试集预算内不超时；把测试集预算调到 2 小时时仍会按预期超时。
- 增加「排队超过 `HE_EVAL_QUEUE_TIMEOUT_SECONDS`」用例，断言以排队超时阻塞，并记录 `queueSeconds`。
- 复用 `apps/api/tests/bugfix-63-real-eval/test_run_evaluations.py` 的基线/终评夹具，确保 #656 的提交时机改动与本 issue 的预算改动可以同时通过。

## 实施步骤

1. 扩展 `EvalStatus` 与 `AiEvalPlatformGateway.get_status`，补解析与回退测试。
2. 在 `Settings` 与 `main.py` 注入三个超时配置，保持旧环境变量缺省可用。
3. 改写 `eval_poller` 的两个 `_expire_*`：执行预算用 `status.started_at`，排队预算用 `eval_started_at`；按 kind 选择预算。
4. 在 `eval_polled` / `eval_timeout` 事件中补 `startedAt`、`elapsedSeconds`、`queueSeconds`、`progressPercent`。
5. 按上面的测试清单补齐单测，并跑 `pnpm test:api` 相关目录。
6. 更新 `.env.example`、04 配置表与 Agent Note；同步英文侧并运行 `pnpm record:i18n`。
7. 部署后对 `01M8DEKFZ5R7` 执行 `/retry`（或新起一个 run）复验：候选评测可以在队列中等待而不被误杀，测试集评测在终评阶段获得完整预算。

## 依赖与交付边界

- 依赖：无代码依赖；与 [#656](https://github.com/Shadow-Azure/harness-evolution/issues/656) 协同验证。若 #656 先合入，本 issue 的测试集预算改动应基于其终评阶段的新提交流程；若本 issue 先合入，#656 仍可独立落地，二者不互相回退。
- 平台状态契约的 `started_at` 是外部依赖：若某次响应缺少该字段，按现有 `eval_started_at` 回退，不新增 HE 数据库列、不阻塞发布。
- 不在本 issue 修改 `ai-eval-platform` 的容量、排队或分片策略；不在本 issue 调整测试集/验证集的工程配置。
- 不改变 `eval_gate.py` 的接纳规则、`init_score/best_score/verdict` 语义或前端展示字段。

## 独立验证

```sh
pnpm lint:api
pnpm typecheck:api
pnpm test:api -- apps/api/tests/m12-03-real-patch-eval apps/api/tests/bugfix-63-real-eval
pnpm verify:flow
pnpm test:gates
pnpm record:i18n -- .agents/notes/implemented/architecture/<agent-note>.md
```

- 新增/修改的 poller 测试全部通过；`fake` 网关构造的「排队 3 小时 + 执行 30 分钟」不会产生 `eval_timeout`。
- 若显式把 `HE_EVAL_TEST_TIMEOUT_SECONDS` 设回 7200，测试集基线执行超过 2 小时仍会超时，证明分档生效而不是简单放大全局值。
- 生产复验：对 `01M8DEKFZ5R7` 或同配置新 run 触发重试，`eval_polled` 事件能看到 `startedAt`/`progressPercent`；测试集基线不再在迭代阶段抢占候选；终评阶段两项测试集评测在各自预算内完成或给出可解释的终态。

## 验收标准

- 一个先排队 100 分钟、再实际执行 90 分钟的候选评测不会被判超时；只有实际执行时间达到候选预算才记 `eval_timeout`。
- 测试集基线与测试集终评使用独立于候选的预算，测试集基线执行超过 2 小时不再自动阻塞 run。
- 排队超过 `HE_EVAL_QUEUE_TIMEOUT_SECONDS` 的评测仍会以明确的排队超时终态结束，不会让 run 永久悬空。
- `eval_timeout` 事件能直接读出 `kind`、`startedAt`、`elapsedSeconds`、`queueSeconds`，运维无需再靠人工对时间线推断。
- 与 #656 同时存在时，启动阶段不提交测试集基线；终评阶段两项测试集评测按新预算执行，门控与终评分数口径不变。

## 门禁与 CI

- 命中 `pnpm lint:api`、`pnpm typecheck:api`、`pnpm test:api`、`pnpm test:gates`、`pnpm verify:flow`、`pnpm verify:docs`；覆盖率达到仓库要求的 80%。
- 新增或修订 Agent Note（`.agents/notes/implemented/architecture/`），并在同一 PR 内更新英文侧与 i18n 记录。
- `.env.example` 与 `plans/fullstack-design/04-backend-architecture.md` 的配置表必须与 `config.py` 默认值一致。
- 涉及真实平台的状态字段解析需有 fake 契约测试，CI 不依赖生产平台。

## 非目标

- 不在本 issue 把 `test_baseline` 从启动阶段移到终评阶段（由 #656 负责）。
- 不修改 `ai-eval-platform` 的资源池、排队、镜像准备或并发策略。
- 不缓存或复用测试集基线分数（可作为后续优化单独评估）。
- 不改变候选与基线的比较规则、主指标或 `verdict` 语义。
- 不为本次事故单独改前端；进度先通过 run events 暴露。
