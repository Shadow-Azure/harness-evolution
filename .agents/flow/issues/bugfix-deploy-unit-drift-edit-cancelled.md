# 部署重启杀死在跑的 edit 子进程：agent-edit 被判终态取消并失败整个自进化 run

[English](bugfix-deploy-unit-drift-edit-cancelled.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-48
milestone: bugfix
depends:
  - bugfix-11
  - bugfix-45
priority: P2
status: ready
scope:
  - deploy/**
  - apps/api/tests/deploy/**
  - docs/deployment.md
  - docs/deployment.en.md
  - docs/deployment.i18n.yaml
  - plans/**
  - scripts/doc-budgets.manifest.json
  - .agents/**
adr: []
github:
  number: 583
  url: https://github.com/Shadow-Azure/harness-evolution/issues/583
```

## 背景

### 问题场景

2026-11-24 16:55:06（+08），生产自进化 run `01M86AXB7180YHS9XY6D67KEG0`（target `codespec-subagent-driven-development@openspec-cn-main-copy-ar-a7ec200-claude-core`，空间 `OpenSpec-cn_SWE-bench`）在第 6/7 步「迭代优化」第 2 轮补丁生成阶段变成终态失败：

- 运行页：`http://8.149.232.63/workspaces/01M7KJ05ENF9784GPBDV544VB0/evolution/runs/01M86AXB7180YHS9XY6D67KEG0`
- 数据库：`status=failed`、`error_stage=patch`、`error_message=claude-code edit call was cancelled`、`error_at=2026-11-24 16:55:06`、`blocked_stage=NULL`、`retry_attempts=0`。
- 轮次：第 1 轮已成功并接纳（候选 85.0 对基线 80.0，最终 commit `c4d3262`）；第 2 轮 `status=failed`（16:41:32 开始、16:55:06 结束、`patch=NULL`）；第 3 轮仍为 `pending`。

### 问题描述

用户看到的是：第 1 轮改动与评测都成功，页面随后在第 6 步报「补丁生成失败」，文案只有 `claude-code edit call was cancelled`；run 没有进入 `blocked`，页面也没有「重试」入口，剩余两个簇永远不会再被处理。这不是模型拒绝、权限拒绝或评测失败，因为同一个 run 的三次 analyze 调用和第 1 轮 edit 调用都成功且有完整 token/费用记录。

持久事件与 job 记录显示这是一次与部署同秒发生的中断：

| 时间（+08） | 事实 |
|---|---|
| 16:31:44 | run 创建，prepare 启动 |
| 16:32:41 | 3 个簇创建完成 |
| 16:36:01 | 第 1 轮 `agent.edit` 成功（`latencyMs=192147`、tokens 86020、cost 1.2078755） |
| 16:36:06 | 候选推送成功，提交评测 |
| 16:41:17 | 评测完成：80.0 → 85.0，`externalVerdict=accept` |
| 16:41:32 | 第 1 轮接纳；第 2 轮 `evolution_advance` job `01M86BF9RNZN7KAMRA95P4Y055` 启动 |
| 16:54:00 | 新 release `6d11b30` 落到 `/opt/harness/releases/` |
| 16:55:05 | `systemctl restart harness-api`：`Stopping harness-api.service`，进程开始 shutdown |
| 16:55:05 | 同一 job 以 `ConfigError: claude-code edit call was cancelled` 失败；`cancel_requested=0` |
| 16:55:06 | run 变成 `failed`，第 2 轮 `failed` |
| 16:55:07 | 新进程启动完成 |

第 2 轮从开始到失败共 814 秒，明显小于 `EDIT_TIMEOUT_SECONDS=1800`，因此不是超时；job 的 `cancel_requested=0`，也不是用户取消。失败发生在部署重启的同一秒。

## 目标

- 让日常发布不再把在跑的 Claude Code 子进程一并 SIGTERM，从而不再把部署中断伪装成 `claude-code edit call was cancelled` 的终态 provider 失败。
- 让 `release.sh` 对 systemd unit 的安装负责：仓库/暂存目录中的 unit 与生产 `/etc/systemd/system/harness-api.service` 不允许无声漂移；漂移时发布失败并保持旧服务，而不是带病重启。
- 用可执行的契约测试锁住三件事：`KillMode=mixed`、`TimeoutStopSec` 大于 drain 窗口、发布在重启前完成 unit 安装与生效校验。
- 修复后，发布窗口内的在跑 edit job 必须走「应用内 drain → `interrupted`」，而不是「systemd 杀子进程 → exit 143 → provider 终态取消」。

## 设计依据

- [01 §6 部署形态与扩展路径](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/01-architecture.md)：单 ECS、release 目录、回滚与发布边界。
- [docs/deployment.md](../../../docs/deployment.md)：发布顺序、回滚、重启排水与 `HE_JOB_DRAIN_TIMEOUT_SECONDS` 的现状说明。
- [bugfix-11 部署重启中断自进化 run](../../../.agents/flow/issues/bugfix-deploy-interrupt-recovery.md)：租约、心跳、drain 与 `KillMode=mixed` / `TimeoutStopSec` 的设计来源；本 issue 修复它未兑现的部署侧安装契约。
- [bugfix-45 部署 provisioning 契约进入 CI](../../../.agents/flow/issues/bugfix-deploy-contract-ci.md)：`apps/api/tests/deploy/` 静态契约测试与 `release.sh` 顺序断言的既有模式。
- [systemd.kill](https://www.freedesktop.org/software/systemd/man/latest/systemd.kill.html)：`KillMode=control-group` 默认向 cgroup 内全部进程发 SIGTERM；`mixed` 只向主进程发 SIGTERM，超时后才对剩余进程 SIGKILL。
- [Claude Code provider 的取消分类](../../../apps/api/app/third_party_api/ai_agent/claude_code.py)：`CANCELLED_EXIT_CODE=143` 被归为 `cancelled` 且 `retryable=False`。

## 根因分析

### 结论

直接原因是**生产 systemd unit 落后于仓库**：`/etc/systemd/system/harness-api.service` 仍是 2026-11-19 安装的旧版本，没有 `#474` 加入的 `KillMode=mixed` 与 `TimeoutStopSec=45`。`release.sh` 的重启因此按 systemd 默认 `KillMode=control-group` 执行，SIGTERM 同时送达 Python 主进程和它启动的 `claude` 子进程；子进程以 143 退出（128+SIGTERM），`ClaudeCodeProvider._call()` 把 143 归一成 `cancelled`（`retryable=False`），最终由 `_fail_patch_generation()` 写成 run 终态失败。

更深一层的契约缺口是：**发布只更新 `current` 软链并重启，从不安装 unit**。`deploy/harness-api.service` 与 `/opt/harness/shared/config/harness-api.service` 已经包含正确配置（16:53 由流水线推送），但 `release.sh` 只做 `systemctl restart`；只有 root 手动重跑 `bootstrap-server.sh` 才会把 unit 装进 `/etc`。于是 `#474` 的停机保护在代码里、在暂存目录里都存在，却在生产上从未生效。

### 分析过程

1. **从运行详情读取失败事实**：`evolution_runs` 的 `error_stage=patch` 与 `error_message=claude-code edit call was cancelled`；`evolution_rounds` 第 2 行 `started_at=16:41:32`、`finished_at=16:55:06`、`patch=NULL`；`job_runs` 的 `01M86BF9RNZN7KAMRA95P4Y055` 同为 `failed`，`error` 与 run 完全一致，`cancel_requested=0`。排除人工取消。
2. **对齐部署时间线**：`journalctl -u harness-api` 显示 16:55:05 `Stopping harness-api.service`，同秒记录 `job execution failed error_type='ConfigError'`，16:55:07 新进程启动；release 目录 `6d11b30` 的 mtime 为 16:54。失败与 `systemctl restart` 同秒，而不是业务超时或外部评测。
3. **读取消分类代码**：`AsyncioClaudeCliRunner` 只有在自身超时或任务被 cancel 时才置 `cancelled=True`；本次运行 814 秒小于 1800 秒，且 handler 没有被 cancel（否则 job 会走 `_run()` 的 `CancelledError` 分支并标记 `interrupted`）。剩下的唯一路径是子进程返回 `143`，由 `_is_cancelled()` 命中 `CANCELLED_EXIT_CODE`。
4. **确认 143 的来源**：`systemctl show harness-api -p KillMode` 返回 `KillMode=control-group`；`/etc/systemd/system/harness-api.service` 的 mtime 是 2026-11-19 23:22；与 `/opt/harness/shared/config/harness-api.service` 做 diff，只差 `KillMode=mixed` 与 `TimeoutStopSec=45` 两行（外加上方注释）。`git log deploy/harness-api.service` 显示这两行由 `#474`（2026-11-21）加入，因此生产 unit 从那天起就没有随发布更新。
5. **确认部署链路不安装 unit**：`deploy/release.sh` 的顺序是 preflight → Alembic → 切换 `current` → `systemctl restart harness-api` → 健康检查；没有任何 `install` 或 `daemon-reload`。`deploy/bootstrap-server.sh` 才会安装 unit，但它是 root 手动执行的一次性初始化；`deploy.yml` 只调用 `release.sh`。因此 `/opt/harness/shared/config/` 的 unit 是新的，`/etc/` 的 unit 是旧的。
6. **串起失败链**：16:55:05 systemd 向整个 service cgroup 发 SIGTERM → `claude` 子进程收到 SIGTERM 并以 143 退出 → `_call()` 走 `_is_cancelled(result)` → `_cancelled_error("edit")` 构造 `retryable=False` 的 `AgentProviderError` → `_handle_provider_failure()` 因不可重试调用 `_fail_patch_generation()` → `ConfigError("claude-code edit call was cancelled")` → run `failed`。由于 handler 本身未被 cancel，`JobRunner._run()` 的 `interrupted` 分支没有机会执行。
7. **排除项**：不是 1800 秒超时（814 秒）；不是模型/鉴权问题（同模型三次 analyze 与第 1 轮 edit 均成功，tokens/费用非零）；不是用户取消（`cancel_requested=0`）；不是 Git/workspace 失败（第 1 轮 candidate 已推送，第 2 轮失败发生在 edit 调用内）；也不是评测失败（第 1 轮评测已 `accept`）。

### 为什么这次看起来像「AI 编辑被取消」

`_cancelled_error()` 对「运行器自身超时/取消」和「子进程被外部 SIGTERM」共用一个文案与同一个 `retryable=False`。本次的真实语义是「服务在部署，systemd 把子进程一起杀了」，但页面只能看到「调用被取消」，于是看起来像模型或 provider 主动取消。这个分类把「可恢复的部署中断」误判成「不可恢复的 provider 失败」，直接导致 run 终态失败，而不是进入 `interrupted` 等待重启后恢复。

## 推荐方案（唯一）

**把 systemd unit 纳入发布契约：`release.sh` 在重启前通过一个受限的 root helper 安装 `$SHARED/config/harness-api.service`、执行 `daemon-reload`，并断言生效配置为 `KillMode=mixed` 且 `TimeoutStopSec` 大于 drain 窗口；任一步失败就中止发布并保留旧服务。**

这直接修复根因：生产 unit 不再落后于仓库，部署重启时 systemd 只向主进程发 SIGTERM，`claude` 子进程不会被一起杀死。主进程收到 SIGTERM 后由现有 `JobRunner.close()` 进行 25 秒 drain；edit 调用被应用自己取消，`ClaudeCliCancelled` 走 `_run()` 的 `interrupted` 分支并写 `job interrupted during shutdown`，不会再产生 143 和 `claude-code edit call was cancelled` 的终态失败。

具体实现：

1. **新增受限的 unit 安装器** `deploy/install-harness-unit.sh`：只接受固定的 `$SHARED/config/harness-api.service`，校验文件包含 `KillMode=mixed`、`TimeoutStopSec` 且其值大于 `HE_JOB_DRAIN_TIMEOUT_SECONDS + 10`，然后 `install -m 0644` 到 `/etc/systemd/system/harness-api.service` 并 `systemctl daemon-reload`；最后用 `systemctl show` 校验 `KillMode=mixed` 与生效的 `TimeoutStopSec`，不满足则以非零退出。
2. **在 bootstrap 中安装 helper 与最小 sudo 权限**：`deploy/bootstrap-server.sh` 把 helper 安装到 `/usr/local/sbin/harness-install-unit`，并为部署账号增加仅允许执行该 helper 的 sudoers 规则；不授予 deploy 任意 `install` / `systemctl daemon-reload` 权限。
3. **在发布流程中调用并验证**：`deploy/release.sh` 在切换 `current` 之前调用 `sudo -n /usr/local/sbin/harness-install-unit`；helper 失败则不切软链、不重启，旧 release 继续服务。成功后在重启前再次断言 `systemctl show -p KillMode --value harness-api` 为 `mixed` 且 `TimeoutStopSec` 足够，否则按发布失败处理。
4. **一次性修复当前生产机**：在 8.149.232.63 上以 root 执行 helper（或重跑 bootstrap）安装当前 unit，确认 `systemctl show -p KillMode` 从 `control-group` 变为 `mixed`；这是本次事故的现场修复，之后由发布流程保证不再漂移。
5. **用契约测试锁住**：新增 `apps/api/tests/deploy/test_unit_install_contract.py`，静态断言 release 在 restart 前调用 helper、bootstrap 安装 helper 与 sudoers、unit 含 `KillMode=mixed` 与 `TimeoutStopSec`、helper 校验生效值；把该测试纳入现有 `deploy-contract` job。
6. **文档同步**：`docs/deployment.md` 与英文侧把发布顺序改为「安装/校验 unit → 迁移 → 切换 → 重启 → 探活」，说明 unit 变更不再依赖人工 bootstrap；补充「旧机器首次升级需要一次 root helper」的说明。

> 本 issue 只做 unit 安装契约与部署验证，不修改 provider 的 143 分类逻辑。原因：修复后 systemd 不再把 SIGTERM 送达子进程，143 路径不会在这次部署场景触发；保留现有分类可避免把用户主动取消误当成可恢复中断。若未来需要覆盖「运维直接 kill 子进程」等场景，应另开 issue 设计 shutdown 感知的中断分类。

## 实现内容

- `deploy/install-harness-unit.sh`：受限安装器与生效校验。
- `deploy/bootstrap-server.sh`：安装 helper 与最小 sudoers。
- `deploy/release.sh`：重启前安装并校验 unit，失败不切换/不重启。
- `apps/api/tests/deploy/test_unit_install_contract.py`：上述契约的静态测试。
- `docs/deployment.md`、`docs/deployment.en.md`、`docs/deployment.i18n.yaml`：发布顺序与升级说明。
- `.agents/notes/`：记录「unit 是发布契约的一部分，不能只靠 root 手工 bootstrap」的决策。

## 实施步骤

1. 写 helper，先在测试机用一份错误 unit 验证「缺少 `KillMode=mixed` 时拒绝安装」。
2. 在 bootstrap 中安装 helper 与 sudoers，确认 deploy 账号只能执行 helper。
3. 改 `release.sh`，把 unit 安装放在 `current` 切换之前，并补生效断言。
4. 加静态契约测试，故意删除 release 中的调用或 unit 中的 `KillMode`，确认测试变红。
5. 更新中英部署文档与 Agent Note。
6. 在生产机执行一次 helper，确认生效值；随后用一次正常发布验证「暂存 unit 与 `/etc` unit 一致」。
7. 在下一次发布窗口启动一个长 edit 调用，确认重启时 job 变为 `interrupted` 而非 `failed`，且事件不再出现 `claude-code edit call was cancelled`。

## 依赖与交付边界

- 依赖：`bugfix-11`（`KillMode=mixed` / `TimeoutStopSec` 的设计）、`bugfix-45`（`apps/api/tests/deploy/` 契约测试与 `deploy-contract` job）。
- 关联但不在本 issue 实现：[#578](https://github.com/Shadow-Azure/harness-evolution/issues/578)（优雅停机写入的 `interrupted` job 需要启动恢复）。本 issue 保证 job 进入 `interrupted` 而不是 `failed`；恢复动作由 #578 负责。
- 生产现场修复需要 root 执行一次 helper 或 bootstrap；之后由每次发布自动保证。
- 不改 `ClaudeCodeProvider` 的 143 分类、`EDIT_TIMEOUT_SECONDS`、drain 窗口、模型调用或评测逻辑。

## 独立验证

静态契约与流程：

```sh
pnpm verify:flow
pnpm verify:flow-online
apps/api/.venv/bin/python -m pytest apps/api/tests/deploy/test_unit_install_contract.py -q
pnpm test:gates
pnpm lint:docs
```

生产只读核对：

```sh
systemctl show harness-api -p KillMode -p TimeoutStopSec
# 修复前：KillMode=control-group，TimeoutStopSec=90（默认）
# 修复后：KillMode=mixed，TimeoutStopSec=45

diff -u /etc/systemd/system/harness-api.service /opt/harness/shared/config/harness-api.service
# 修复后：无差异
```

部署行为验证（测试机）：

```sh
# 1. 启动一次跨发布窗口的 evolution edit 调用
# 2. 在 edit 进行中执行 deploy/release.sh
# 3. 重启完成后检查 run / job：
#    - job.status = interrupted，error = job cancelled during shutdown
#    - run 不出现 error_stage=patch / claude-code edit call was cancelled
#    - 若 #578 已合并，启动后出现 job_recovered 并继续第 2 轮
```

- 预期：unit 安装失败时 release 在切换前退出、旧进程继续服务；unit 正常时重启不产生 143 子进程退出；job 走 `interrupted`。

## 验收标准

- [ ] 生产 `systemctl show harness-api -p KillMode` 为 `mixed`，`/etc` unit 与 `$SHARED/config` unit 无差异。
- [ ] `release.sh` 在 `systemctl restart` 之前安装并校验 unit；unit 缺失/取值错误时发布失败且不切换 `current`。
- [ ] 契约测试在「release 未调用 helper」「unit 缺 `KillMode=mixed`」「`TimeoutStopSec` 不大于 drain 窗口」三种情况下失败。
- [ ] 发布窗口内的在跑 edit job 以 `interrupted` 收尾，run 的 `error_message` 不再是 `claude-code edit call was cancelled`。
- [ ] 发布文档的中英两侧同步说明 unit 安装步骤；Agent Note 记录该决策。
- [ ] 不引入 deploy 账号的广泛 root 权限。

## 门禁与 CI

- `pnpm verify:flow`、`pnpm verify:flow-online`、`pnpm test:gates`
- `pnpm test:api -- tests/deploy/test_unit_install_contract.py`
- `deploy-contract` CI job（现有 `apps/api/tests/deploy` 测试）
- `pnpm lint:docs`、`pnpm verify:docs`
- 文档预算：`docs/deployment.md` 修改后运行 `pnpm record:i18n -- docs/deployment.md` 并更新预算清单；覆盖率不低于 80%。

## 非目标

- 不修改 provider 对退出码 143 的取消分类；不把取消改成重试。
- 不延长或缩短 `HE_JOB_DRAIN_TIMEOUT_SECONDS` / `EDIT_TIMEOUT_SECONDS`。
- 不实现 #578 的 `interrupted` 启动恢复；不重跑本次已失败的 run。
- 不冻结发布窗口，不要求人工等待 run 结束才能部署。
- 不给 deploy 账号开放任意 `install`、`systemctl` 或 root shell 权限。
- 不修改模型、prompt、patch 生成、评测或前端展示。
