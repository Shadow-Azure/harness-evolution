# Claude Code 版本目录对服务账号可执行

[English](bugfix-claude-code-shared-permissions.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-28
milestone: bugfix
depends:
  - bugfix-26
priority: P2
status: done
scope:
  - .agents/**
  - plans/**
  - deploy/**
  - .github/workflows/**
  - apps/api/tests/**
  - docs/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-23-claude-code-shared-directory-permissions.md
github:
  number: 531
  url: https://github.com/Shadow-Azure/harness-evolution/issues/531
```

## 背景

2026-11-23 14:22，生产 run `01M83H4MV03G85R4SD5K91CK80` 在聚类阶段失败：`cluster cluster.review failed: AgentProviderError: claude-code analysis call could not start`。`ai_agent_call` 显示 `cluster.review` 在 10ms 内失败、0 tokens、`model=unknown`，随后 `run_failed` 记录 `stage=cluster`。这是进程在 spawn 阶段就失败，不是模型、网络或密钥问题。

同一失败在 #526 部署前已经出现：10:40 的 run `01M834EBAY3C9BB3TM8V85VHQN` 与 14:06 的 run `01M83G629FXGVG2V64AYXYAHP0` 都发生 `cluster.review` / `cluster.score` / `severity.score` 三次 `outcome=error`（7–10ms、0 tokens），但被静默降级为兜底 confidence/severity，run 仍 completed、终评 85 分。#526 把真实 provider 的失败策略改成 strict，并把 CLI/settings 切到服务级共享路径，失败才第一次显式暴露。因此 #526 是可见性触发器，不是能力故障的制造者。

直接原因：`deploy/install-claude-code.py` 的 `install_from_deb()` 用 `tempfile.mkdtemp()`（默认 0700）解包 deb，再用 `os.replace(staging, target)` 直接把 staging 改名为 `/opt/harness/shared/claude-code/<version>`，版本目录保留 0700、属主 deploy。服务以 `harness` 用户运行（`User=harness`，无 home、无 ACL、与 deploy 不同组），无法穿越该目录执行 `current/usr/bin/claude`；`execve` 返回 EACCES，Python 归一成 `OSError`，最终变成 `AgentProviderError: claude-code analysis call could not start`。

为什么部署仍是绿的：#526 新增的 `preflight_shared_access()` 只检查 `prefix`、`config`、settings 文件和二进制 other 位，不检查 `<version>` / `usr` / `usr/bin`；`deploy.yml` 的预检用 `test -x "$BIN"`，以 deploy 身份通过 SSH 执行，deploy 是目录属主，必然通过；安装器自身的 `--version` 也是 deploy 视角。真正执行 CLI 的是 harness，缺少一次服务账号视角的验证。

结论：根因是 #379 引入的安装器权限处理（版本目录 0700）；#526 的修复方向正确，但新增的预检漏掉了版本目录，且没有修复已存在的 0700 目录，所以“换了路径仍然起不来”。只改 preflight 不够：当前部署走 `need_install=false` 的仅配置路径，脚本不会进入 `install_from_deb()`，已有目录必须单独修复。

### 根因定位过程

1. 读生产 run `01M83H4MV03G85R4SD5K91CK80` 的事件：seq 6 是 `cluster.review` 的 `ai_agent_call`，`outcome=error`、`latencyMs=10`、`totalTokens=0`、`model=unknown`；seq 7 是 `run_failed`，`stage=cluster`，错误为 `ClusterAIFailure` 包裹 `AgentProviderError: claude-code analysis call could not start`。`/steps/clusters` 返回 `failurePolicy=strict`、`clusters=[]`、`failure` 同文。
2. 对比 #526 部署前的 run：`01M834EBAY3C9BB3TM8V85VHQN`（10:40）和 `01M83G629FXGVG2V64AYXYAHP0`（14:06）都有三次 `error`，`degraded.reason` 均为 `AgentProviderError: claude-code analysis call could not start`，但两次 run 都 completed，证明“CLI 起不来”早于 #526，且此前被静默降级掩盖。
3. 读 Deploy run `45121827113`（sha `8e907591`）：安装器输出 `shared-settings: /opt/harness/shared/claude-code/config/settings.json` 与 `stable-binary: /opt/harness/shared/claude-code/current/usr/bin/claude`；预检打印“共享资产预检通过”；注入 11 个配置项，含 `HE_AI_AGENT_CLAUDE_BIN`、`HE_AI_AGENT_CLAUDE_SETTINGS`、`CLAUDE_CONFIG_DIR`、`ANTHROPIC_API_KEY`；14:07:15 重启 `harness-api` 并探活成功。也就是说 env、软链、部署流水线都成功，问题只在服务账号执行视角。
4. 读安装器代码：`install_from_deb()` 创建 0700 staging 后 `os.replace()` 保留权限；`binary.exists()` 成功时直接返回，重跑不会修已存在目录；`preflight_shared_access()` 只检查 `prefix` 与 `settings.parent`，不检查版本目录和 `usr` / `usr/bin`。
5. 核对线上部署的 `claude-code_2.1.323-1` deb：`data.tar.gz` 没有 `./` 根条目，首个条目是 `./usr`，解包不会通过根条目把 staging 改回 0755；`usr/bin/claude` 为 0755。结合 `mkdtemp()` 的 0700，版本目录保留 0700。
6. 结论：harness 无法执行共享路径上的 CLI；修复要同时覆盖“新解包”和“已存在目录”两条路径，并让预检覆盖整条目录链。

### 用户要求

- 直接解决根因，不要只补 Secret、只改文档或只加提示。
- 优先纯流水线：能通过重跑 Deploy 完成，就不要人工上服务器；如果必须 root 或手工步骤，明确最小步骤、原因和回退方式。
- 不 fake：真实 provider 下失败必须显式失败，不得落兜底 confidence/severity，不得显示“自进化有效”。
- 可验证：部署后真实 run 的 `cluster.review` 为 `outcome=ok`、tokens>0、model 非 unknown，且不出现 `could not start`。
- 保持安全边界：保留 deploy/harness 两个用户和最小权限；不接受 0777、服务直接用 deploy 运行、或把密钥写进仓库。

## 目标

- 让 harness 能执行 `/opt/harness/shared/claude-code/current/usr/bin/claude`，版本目录及其祖先目录对服务账号可穿越。
- Deploy 在切换 `current` 前发现“服务账号不可执行”并中止，而不是部署绿灯、运行时才失败。
- 修复覆盖 `need_install=false` 的重复部署：历史 0700 目录在重跑 Deploy 后被修复，无需 root 或手工 chmod。
- 真实 run 的 `cluster.review` 变成 `outcome=ok`、tokens>0、model 非 unknown，且不产生 `degraded`。

## 设计依据

- [07 §5.5.1 AI Agent Provider 出站适配层](../../../plans/fullstack-design/07-backend-implementation.md)：provider 契约、`cluster.review` / `cluster.score` / `severity.score` 任务键与失败归一化。
- [07 §5.5.2 聚类三层：分组 / 审查 / 评分](../../../plans/fullstack-design/07-backend-implementation.md)：真实模式下 review / score / severity 的 strict 失败语义。
- [docs/claude-code.md](../../../docs/claude-code.md)：服务级 CLI 资产的安装、共享 settings、预检与验证命令的现状说明。
- [bugfix-ai-agent-real-mode-no-degrade](bugfix-ai-agent-real-mode-no-degrade.md)：strict 失败策略与 shared `current` 路径的上游决策；本 issue 补它的部署权限缺口。

## 实现内容

- `deploy/install-claude-code.py`：解包后把版本目录（含 `usr`、`usr/bin`）设为 0755；`binary.exists()` 早返回分支也要修复已存在的版本目录权限。
- `deploy/install-claude-code.py`：仅配置路径（`need_install=false`，不传 `--deb`）也要定位 `current` 指向的版本目录并修复权限，保证重跑 Deploy 能修历史 0700 目录。
- `deploy/install-claude-code.py`：`preflight_shared_access()` 从 `prefix` 到 binary 逐级检查 other-exec（至少覆盖 `<version>`、`usr`、`usr/bin`），同时保留 settings 的 other-read 检查；失败在 `switch_current` 之前抛出。
- `.github/workflows/deploy.yml`：预检不再只用 `test -x`（deploy 视角），改为检查路径各级的 `stat` other 位；若 deploy 有权限，增加 `sudo -u harness .../current/usr/bin/claude --version` 冒烟。
- `apps/api/tests/deploy/test_install_claude_code.py`：新增“0700 版本目录必须让预检失败”的用例；新增“`install_from_deb()` 后版本目录为 0755”的断言；修正现有夹具在预检前手动 chmod 0755、掩盖真实缺陷的问题。
- `docs/claude-code.md` / `docs/claude-code.en.md`：更新预检与验收说明，明确版本目录权限和 harness 视角的验证命令。
- `.agents/notes/`：记录“预检必须覆盖整条路径、安装器必须修复已存在版本目录”的决策。

## 实施步骤

1. 修改 `install_from_deb()` 与已有目录路径，统一修复版本目录及祖先目录权限。
2. 扩展 `preflight_shared_access()`，并同步 `deploy.yml` 的预检。
3. 补安装器与预检测试，覆盖真实 0700 场景和安装后 0755。
4. 更新 `docs/claude-code.md` / `.en.md` 与 Agent Note。
5. 重跑 Deploy；按“独立验证”确认 harness 可执行、真实 run 成功。
6. 若验证仍失败，再检查运行进程是否拿到 `HE_AI_AGENT_CLAUDE_BIN`（systemd `EnvironmentFile` 与重启时序），但不再改 CLI 路径。

## 依赖与交付边界

- 依赖：bugfix-26（#521 / #526 已合入）。
- 非目标：不改 provider 契约、聚类算法或 strict/degrade 语义；不新增 Secret；不让服务以 deploy 运行；不使用 0777；不把密钥写入仓库；不改 patch/edit 语义；不重构版本保留策略。

## 独立验证

```sh
# 1) After deployment, verify from the service account's viewpoint
ssh deploy@<host> '
  ver=$(readlink -f /opt/harness/shared/claude-code/current)
  stat -c "%a %U:%G %n" "$ver" "$ver/usr" "$ver/usr/bin" "$ver/usr/bin/claude"
  sudo -u harness "$ver/usr/bin/claude" --version
'
# Expected: the version directory is 755; harness prints 2.1.323 (Claude Code)

# 2) Real-run acceptance
# Start a cluster-only preview or self-evolution run and check the events:
# ai_agent_call: task=cluster.review, outcome=ok, totalTokens>0, model != unknown
# No degraded and no AgentProviderError ... could not start
```

- `pnpm test:api -- tests/deploy/test_install_claude_code.py`
- `pnpm test:gates`
- `pnpm verify:flow`
- `pnpm verify:docs`

## 验收标准

- 部署后 `sudo -u harness /opt/harness/shared/claude-code/current/usr/bin/claude --version` 成功；版本目录及 `usr`、`usr/bin` 为 0755。
- 版本目录为 0700 时预检失败，且失败发生在切换 `current` 之前；不再出现“部署绿但服务不可执行”。
- `need_install=false` 的重复部署能修复历史 0700 目录。
- 真实 run 的 `cluster.review` 为 `outcome=ok`、tokens>0、model 非 unknown；无 `degraded`。
- 单测覆盖 0700 预检失败与安装后 0755；`docs/claude-code.md` / `.en.md` 同步。

## 门禁与 CI

- `pnpm test:api -- tests/deploy/test_install_claude_code.py`
- `pnpm test:gates`
- `pnpm verify:flow`
- `pnpm verify:docs`
- 提交与 PR 标题含 `(#531)`；检视按 `docs/review.md` 执行，检视文档落 `plans/`。

## 非目标

- 不在本 issue 内改 `AgentProviderError.detail` 的暴露、`/api/health` 的 AI Agent 字段或启动 health 的 UI 展示（可另开观测性 issue）。
- 不改模型、网关、base URL 或密钥配置。
- 不引入 root/ACL/`LoadCredential` 方案；优先纯流水线。
- 不重写安装器的版本保留策略或 deploy/harness 用户模型。
