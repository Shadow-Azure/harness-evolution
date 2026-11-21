# 部署重启中断自进化 run：任务租约、心跳与自动续跑

[English](bugfix-deploy-interrupt-recovery.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-11
milestone: bugfix
depends:
  - bugfix-09
  - m5-11
priority: P2
status: done
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - deploy/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/**
  - scripts/doc-budgets.manifest.json
adr: []
github:
  number: 474
  url: https://github.com/Shadow-Azure/harness-evolution/issues/474
```

## 背景

2026-11-21 16:07（+08），生产一次自进化 run `01M7YJAGVW1QKDMA7ECEX1EHT7`（target `skill:systematic-debugging@v6.4.1`）在 prepare 阶段以 `blocked(push)` + `run branch publication failed` 结束。此前 #457 的多托管 push provider（PR #465，merge commit `32170f9`）已于 15:07 合入、15:17 部署成功，因此需要判断是 provider 失效，还是另一类中断。

### 现象

- run API/事件：`status=blocked`、`blockedStage=push`、`push_status=failed`；事件到「聚类完成」后直接是 `run branch publication failed`，没有 `workspace_prepared`，说明 prepare 的 publish 环节没有正常收尾；run 详情只保留通用文案。
- GitHub 侧：fork `Shadow-Azure/superpowers` 创建于 16:07:22（run 创建后 2 秒）；run 分支 `evo/20261121-01M7YJAGVW1QKDMA7ECEX1EHT7` 于 16:07:32 已存在，head `5bf4e780` 正是 `v6.4.1` 标签提交。说明 `ensure_fork`、PAT、push URL 与远端写入都成功。
- 部署侧：Deploy #156（发布 `136aa92`）在 16:07:33.077 切换 current、16:07:33.080 重启 `harness-api`；run 的 `error.at` 同为 16:07:33（+08），与重启同一秒。
- 代码/停机路径：`_push_run_branch` 的 `git push` 是 prepare 的最后一步；`harness-api.service` 未覆盖 systemd 默认的 `KillMode=control-group`，重启会把 git 子进程一并终止；应用 shutdown 的 `jobs.close()` 也会取消在跑任务。远端 ref 已写入、但客户端在收尾阶段被终止时，`git push` 返回非零，被 `classify_git_failure` 归为 `blocked(push)`。
- 文案覆盖：`_prepare_workspace` 先 `mark_blocked()` 写入详细原因，随后 `RunBlocked("run branch publication failed")` 在 job 层再次 `record_blocked()`，用通用文案覆盖了 `error_message`/`push_error`；`GitOperationError` 只保留固定短语、不保留 stderr，因此 API/UI 无法区分「部署重启打断」与「权限/网络失败」。

### 根因分析过程与结论

排查按「先证明 provider 是否生效，再定位失败点」推进：

1. 读 run 详情与事件，确认失败阶段是 push 且 prepare 没有完成；
2. 查 fork 与 run 分支，确认远端已经写入，排除 PAT、fork、push URL、非快进等 provider 侧原因；
3. 对齐 Deploy #156 的 release 日志与 run 的 `error.at`，发现重启与失败同一秒；
4. 读 `GitWorkspaceManager`、`jobs` 与 systemd unit，确认 git 子进程会随服务重启被终止，push 非零后走 blocked 路径，并被通用文案覆盖。

**结论**：本次不是 #457/#465 的 provider 失效。直接原因是 run 与 Deploy #156 的发布窗口重叠，`harness-api` 在 16:07:33.080 重启，终止了正在收尾的 `git push`；远端分支已更新但客户端非零退出，于是被记为 `blocked(push)`。次要问题是中断与真实推送失败没有被区分，且详细错误被覆盖，导致事故看起来像 provider 故障。

**限制**：没有 SSH 进入生产机，未读取 `journalctl` 或 git 原始 stderr；结论基于秒级时间对齐、远端分支已存在、prepare 未完成三组证据与停机代码路径。未实际触发该 run 的重试。

### 为什么需要独立 issue

- 代理/凭据问题已由 #457 修复，但部署重启仍会让 in-flight job 进入 blocked，需要人工 retry；同类中断还会发生在迭代、评测、终评。
- 中断被记为 blocked 且详情丢失，无法区分「部署重启打断」「网络失败」「权限不足」，运维只能靠猜。
- 长期解法是让任务可恢复（租约 + 心跳 + 自动续跑），而不是继续加 retry 或依赖人工冻结部署。

## 目标

- job 具备租约（lease）+ 心跳（heartbeat）：领取任务时写入 lease owner/expiry，执行期间定期续约；进程退出后租约过期，任务可被重新领取。单实例部署先以启动恢复为主，租约字段为后续多实例/异常检测保留。
- 进程启动或重启时自动恢复被中断的 job：不再标 `failed`/`blocked` 等人工，按阶段检查点自动续跑；run 使用既有 `interrupted` 状态并记录 `run_interrupted` / `job_recovered` 事件。
- 关键阶段幂等：
  - prepare/push：持久化 run 的 push target、base commit 与 run branch；恢复时先 `ls-remote` 对账，远端 ref 已是目标提交则跳过 push，否则重推，禁止重复创建分支/重复提交。
  - 迭代/评测/终评：以 round、candidate tag、eval request 为幂等键；恢复时复用已提交的 candidate/tag 与已完成 eval 结果，不重复调用模型或评测。
- 停机语义：SIGTERM 后停止领取新 job，给 in-flight job 一个有限 drain 窗口；窗口内完成则正常结束，未完成则释放租约并标 `interrupted`，由恢复流程接管。部署单元配合 `KillMode=mixed` + `TimeoutStopSec`，避免默认把 git 等子进程一并杀掉。
- 错误分类与可观测：区分 `interrupted`（进程/部署中断）与真实 `blocked(push)`（权限/网络/非快进）；保留详细错误（事件 `error_detail`），不再被通用 `RunBlocked` 文案覆盖；UI 能显示「因部署重启中断，自动恢复中/已恢复」。
- 兼容：不改变 #457 的 provider、fork 与凭据注入语义；真实权限/网络失败仍进入 blocked 并可人工重试；已有 run/job 数据可迁移。

## 设计依据

- [07 §5.8.1 阻塞重试策略](../../../plans/fullstack-design/07-backend-implementation.md#581-阻塞重试策略)：现有 blocked/retry 语义，本 issue 在其上增加可恢复执行，不替代它。
- [07 §5.6 单轮执行](../../../plans/fullstack-design/07-backend-implementation.md#56-单轮执行candidate--push--提交评测fullevolutionengineadvance_one_round)：candidate → push → eval 的阶段边界与幂等点。
- [06 §3.9 job_runs](../../../plans/fullstack-design/06-database-design.md#39-job_runs--统一任务表)：现有 job 状态与字段；本 issue 增加 lease/heartbeat 字段。
- [06 §5.7 evolution_run_events](../../../plans/fullstack-design/06-database-design.md#57-evolution_run_events--执行过程与异常追加)：`run_interrupted`/`push_*` 事件与 `error_detail` 的落库口径。
- [04 §3 分层与目录](../../../plans/fullstack-design/04-backend-architecture.md#3-分层与目录)：job/lease 留在 service 与 db 层，git 进程与 host 差异留在 third_party_api。
- systemd 停机语义：[systemd.kill](https://freedesktop.org/software/systemd/man/247/systemd.kill.html)（默认 `KillMode=control-group`；`mixed` 只向主进程发 SIGTERM，超时后再对剩余进程 SIGKILL）。
- Kubernetes 优雅终止：`terminationGracePeriodSeconds` 与 `preStop` 的 drain 模式，[Pod lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination)。
- 持久执行的任务重试与恢复模式：[Temporal failures and error handling](https://docs.temporal.io/encyclopedia/failures-and-error-handling)。

## 实现内容

### 1. job 租约与心跳

- `job_runs` 增加 `lease_owner`（实例/任务标识）、`lease_expires_at`、`heartbeat_at`；迁移新增字段与 `(status, lease_expires_at)` 索引，历史行按已过期处理。
- `JobRepository.claim()` 从「只认 queued」改为「queued 或 lease 过期的 running」原子领取；`renew()` 周期续约；`release()` 在停机时释放租约但保留可恢复状态；worker 崩溃后由下一次启动或扫描接管。
- 单实例下启动恢复仍以「所有 residual running 都是本进程遗留」为主，租约用于显式表达过期与未来多实例安全。

### 2. 启动恢复与自动续跑

- `JobRunner.recover()`：把 residual running job 标 `interrupted`、记录 `run_interrupted` 事件，并把可恢复的 evolution job 重新入队（替换当前只重排 `sync` 的 `_INTERRUPTIBLE_KINDS`）。
- 恢复入口按阶段进入 `EvolutionPrepareService` / `EvolutionCandidateService` / apply/final，复用已持久化的 workspace、round、candidate、eval 记录；不从头重跑七步。
- run 状态：使用既有 `interrupted` 展示中断，恢复后回到 `running`；事件里保留 `jobId`、`stage`、`attempt`，便于 UI 关联。

### 3. 推送对账与幂等

- 在 `third_party_api/git/workspace.py` 增加只读对账：`remote_ref_commit()` 已能读远端 ref；`prepare` 在 push 前持久化目标 commit 与 push URL，恢复时先比较远端 head：
  - 远端等于目标 commit → 视为已发布，直接继续；
  - 远端缺失或落后 → 走现有快进 push；
  - 远端不可快进 → 仍按真实 push 失败处理，不吞错。
- `git push` 返回非零时，先做一次 `ls-remote` 对账再决定是否 failed：远端已是目标提交则按成功继续（覆盖「远端已写入、客户端被杀」这一类）。
- candidate tag / final 分支使用同一幂等键（candidate ref + commit、run branch + commit），恢复时复用已存在的 ref，不重复 amend/force-push。
- provider 接口与凭据语义不变；对账只读，不把 token 写入 URL/日志/事件。

### 4. 停机 drain 与部署配合

- 应用 shutdown：先停止领取新 job，等待 in-flight job 到 `drain_timeout`；超时后释放租约、标 `interrupted`，再由启动恢复接管。当前 `jobs.close()` 直接 cancel，需要改为有界 drain。
- systemd：`deploy/harness-api.service` 增加 `KillMode=mixed` 与 `TimeoutStopSec`（大于 drain 窗口），让主进程先收到 SIGTERM 并完成 drain，git 等子进程不被默认一起杀；`release.sh` 的迁移/切换/健康检查/回滚顺序不变。
- 部署侧可选的排队/冻结（本 issue 不实现）：在 drain 就绪前，运维仍应避免在发布窗口启动新 run。

### 5. 错误分类、事件与 UI

- `classify_git_failure` 保持「真实 push 失败 → blocked(push)」；新增「进程/部署中断」分类，修复 `_prepare_workspace` 的详细 message 被 job 层 `RunBlocked` 覆盖的问题：blocked 记录只在真实失败时写，中断走 `run_interrupted`。
- 事件保留 `error_type`、`error_message`、`error_detail`；push 事件记录 remote、branch、commit、对账结果（不记录 token）。
- run 详情/列表展示「部署重启中断，已自动恢复/恢复中」，并提供事件时间线；不把中断显示成通用的 `run branch publication failed`。
- 若需新增契约字段/状态（如恢复次数、恢复来源），先改 `packages/contracts` 再 `pnpm contract:generate`；不改变现有 blocked 字段语义。

## 实施步骤

1. 数据模型与迁移：lease/heartbeat 字段、索引、`claim/renew/release` 原子操作与测试。
2. 启动恢复：residual running → interrupted + 自动重排，覆盖 restart during prepare/advance/apply/final 的测试。
3. prepare/push 幂等与对账：持久化 push 目标与目标 commit；模拟「远端已更新但 push 非零」；复用远端 ref，不重复 push。
4. 停机 drain：停接单、有界等待、释放租约；systemd `KillMode=mixed`/`TimeoutStopSec`；部署脚本与文档同步。
5. 迭代/评测/终评恢复：以 round/candidate/eval 为幂等键，复用已完成结果，补恢复测试。
6. UI 与 API：中断/恢复中/已恢复状态、事件时间线、错误详情展示；契约按需更新。
7. 文档与 Agent Note（architecture）：记录 lease/恢复边界、单实例假设与后续多实例演进；补齐门禁与 E2E。

## 依赖与交付边界

- 依赖：#457（bugfix-09，多托管 provider 与 per-run push 目标）与 m5-11（#60，blocked 退避、事件与进程恢复的既有语义）。
- 交付边界：本 issue 只做任务可恢复与中断语义，不引入外部工作流引擎，不改 provider/fork/PAT 注入，不做多实例 leader election，不实现部署冻结/发布窗口的产品化。
- 分阶段：prepare/push 的恢复与对账必须先交付并可独立验收；迭代/评测/终评恢复可在同一 issue 内后续提交，但不能只加 lease 而没有恢复能力。
- 真实权限不足、网络失败、非快进仍按 blocked + 人工 retry；不能把真实失败自动重试成成功。

## 独立验证

```sh
pnpm test:api -- tests/bugfix-11-durable-jobs
pnpm test:api -- tests/bugfix-11-prepare-resume
pnpm test:db
pnpm test:web
pnpm test:e2e -- --pattern bugfix-11
pnpm typecheck
pnpm contract:check
pnpm verify:flow
```

- 模拟远端分支已更新但 `git push` 返回非零：恢复时 `ls-remote` 对账命中，跳过重复 push，run 继续，不进入 blocked。
- 模拟进程重启时 job 处于 running：启动恢复标 interrupted、记录 `run_interrupted`、自动重排；恢复后从 prepare/push 或对应阶段继续，不从头重跑。
- 模拟真实 403/非快进：仍进入 `blocked(push)`，错误详情可在事件/详情中看到，不被通用文案覆盖。
- 模拟停机 drain：SIGTERM 后在窗口内完成则正常结束；超时则释放租约、标 interrupted，下次启动接管。
- 数据：迁移前后 job/run 可读；无 lease 的历史行按过期处理；SQLite 与 MySQL 迁移测试通过。
- UI：run 详情显示中断/恢复中/已恢复，不显示误导性的通用 push 失败。

## 验收标准

- 部署重启（或 `kill -TERM`）发生在 prepare/push 后，run 无需人工 retry 自动继续；远端 ref 与目标 commit 一致，不重复 push、不创建重复分支。
- 重启发生在迭代/评测/终评，恢复后复用已完成的 candidate/tag/round/eval，不重复调用模型或评测（以幂等键与事件断言）。
- 中断与真实失败可区分：中断为 `interrupted` 并可自动恢复；权限/网络/非快进仍为 `blocked(push)` 且保留详情。
- 停机 drain 有上限，部署不会无限等待；超时后 job 安全释放并由恢复流程接管。
- 迁移、事件、API、UI、文档与门禁齐全；现有 blocked/retry 与 provider 行为不回归。

## 门禁与 CI

- `pnpm test:api`、`pnpm test:db`、`pnpm test:web`、`pnpm test:e2e`、`pnpm typecheck`、`pnpm contract:check`（契约变化时）、`pnpm verify:flow`、`pnpm lint:docs`、`pnpm test:gates`。
- 新增的 restart/resume 测试必须进入 CI；迁移测试覆盖 SQLite/MySQL；不把生产日志、Session 内容或凭据写入仓库。

## 非目标

- 不引入 Temporal/Celery 等外部编排；不做多实例 leader election 或分布式锁（单实例 lease 先落地，后续再演进）。
- 不改变 #457 的 provider、fork、PAT 注入与既有错误分类语义。
- 不把真实权限/网络失败自动重试成「成功」；blocked 仍是人工处理路径。
- 不做部署冻结/发布窗口的产品化；运维可先用部署排水缓解。
- 不重构七步引擎的算法、UI 或评测协议。
