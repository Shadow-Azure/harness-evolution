# 真实 AI 模式下聚类失败必须显式失败，不得静默降级

[English](bugfix-ai-agent-real-mode-no-degrade.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-26
milestone: bugfix
depends:
  - bugfix-15
  - bugfix-17
  - bugfix-19
  - bugfix-23
priority: P2
status: ready
scope:
  - apps/api/app/service/evolution/**
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/app/config.py
  - apps/api/tests/**
  - packages/contracts/**
  - apps/web/**
  - deploy/**
  - docs/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 521
  url: https://github.com/Shadow-Azure/harness-evolution/issues/521
```

## 背景

用户在生产 run `01M834EBAY3C9BB3TM8V85VHQN`（2026-11-23 10:40，目标 `codespec-subagent-driven-development`）里看到聚类置信度仍是 `0.82`、严重度仍是 `10.0`，怀疑聚类和置信度环节还在走打桩代码。实际排查发现：代码已经接入真实 provider，但三次真实调用全部失败，系统按现有设计静默降级成确定性兜底值，页面仍显示“✓ 已完成 · 自进化有效”。用户明确要求：**在有配置说不要 fake 的情况下，不要降级**；并进一步追问 deploy 与运行用户为什么是两个、是否正常、能否只用部署流水线根治。

### 问题描述：deploy 与 harness 是两个用户

- `deploy` 是 SSH/发布账号：拥有 `/opt/harness`，负责写 release、注入 `.env`、重启服务；M15 也以它安装 Claude Code，写到 `/home/deploy/.local/bin/claude` 与 `/home/deploy/.claude`（目录 0700，settings/api-key 0600/0700）。
- `harness` 是服务账号：`deploy/harness-api.service` 的 `User=harness`；bootstrap 用 `useradd --system --no-create-home --shell /usr/sbin/nologin` 创建，没有 home，也没有 deploy 的目录权限。服务进程由 systemd 以它启动，负责 API worker、聚类 AI 调用和 git workspace。
- provider 的默认路径是 `~/.local/bin/claude`，`Path(configured).expanduser()` 在 harness 下展开成 `/home/harness/.local/bin/claude`（不存在）；`ClaudeCodeProvider._settings_file()` 固定读 `Path.home()/".claude"/settings.json`，即 `/home/harness/.claude/settings.json`（也不存在，且它根本不会去 deploy 的 home）。
- 于是 3 次真实调用都在 spawn 阶段失败（`could not start`，7–8ms，0 tokens）；`cluster_llm` 按现有设计把失败折叠成 0.82/10.0 兜底值；页面看不到降级，仍显示“自进化有效”。用户因此感觉“还是打桩”。

### 根因

1. **资产归属错配（直接原因）**：Claude Code 是“deploy 用户的用户级工具”，不是“harness 可用的服务级资产”。M15 的安装/配置都写在 deploy 的 home；provider 又只认服务用户的 home；两者之间没有共享路径、组、ACL 或可配置 settings 路径。
2. **职责边界空白（结构原因）**：M15 的非目标明确“不把 Claude Code 接进 harness-api”；#492（bugfix-17）的 scope 只到 `apps/api` 的 provider 子类；#499 只负责把三个键注入 `.env`；`docs/deployment.md` 把“稳定路径与共享 settings”指给 bugfix-17/M15，但两者都没有包含它。结果没有 issue 真正拥有“让 harness 能执行 CLI、读到 settings/凭据”这一步。
3. **默认值与 systemd 环境（放大原因）**：`HE_AI_AGENT_CLAUDE_BIN` 默认 `~/.local/bin/claude`；`HE_AI_AGENT_CLAUDE_SETTINGS` 不存在；systemd 系统服务不继承登录 shell 的 HOME/PATH，`~/.local/bin` 和 deploy 的 bin 都不在 PATH；CLI 的 settings/api-key 在 0700 目录、0600 文件，属主 deploy。
4. **静默降级（结果原因）**：`cluster_llm` 对 review/score/severity 的异常一律 catch 后返回 fallback；`prepare` 照常落库并写 `clusters_created`；API/UI 不暴露 `degraded`；run 终态又由 fake 评测推出“自进化有效”。真实失败被伪装成正常结果。
5. **不是“两个用户”本身的错**：deploy/运行用户分离是标准的最小权限做法；如果让服务用 deploy 跑，服务被利用时会连带拿到 deploy 的 home、SSH 部署凭据和写发布权限，风险更大。问题在于“用户级 CLI/配置”没有升级为“服务级资产”，以及失败被静默吞掉。

### 分析过程

1. 读生产 run 的 `events`：seq 6/8/10 分别是 `cluster.review`、`cluster.score`、`severity.score` 三次 `ai_agent_call`，provider 都是 `claude-code`，outcome 都是 `error`，耗时 7–8ms，`model=unknown`，`inputTokens=0`、`outputTokens=0`、`costUsd=0`；seq 7/9/11 是三条 `degraded`，原因统一为 `AgentProviderError: claude-code analysis call could not start`；seq 12 的 `clusters_created` 仍落 `algorithm=hybrid-lexical-llm-v1`，但 `degraded=[cluster.review, cluster.score, severity.score]`。
2. 读部署日志：最近两次成功的 Deploy（`45101610757` / `45099843286`）都显示 `claude-code 2.1.323` 已安装、`settings: /home/***/.claude/settings.json`，但 `AI Agent Secret：0/3 已写入、其余已移除`；`CLAUDE_CODE_MODEL`、`CLAUDE_CODE_API_KEY`、`CLAUDE_CODE_BASE_URL` 三个 Secret 已配置。
3. 读配置与部署拓扑：`Settings` 默认 `ai_agent_provider=claude-code`、`ai_agent_claude_bin=~/.local/bin/claude`；`deploy/harness-api.service` 是 `User=harness`；bootstrap 用 `useradd --system --no-create-home`；M15 installer 以 deploy 写 `~/.claude` 并 chmod 0700；`deploy/harness-api.service` 没有 `Environment=HOME` 或额外 PATH。
4. 读聚类与 provider 代码：`prepare.py` 在 `agent is None` 时走词面路径，否则走 `_enhance_clusters`；`cluster_llm.py` 对 `cluster.review` 失败回退词面草稿，对 `cluster.score` 失败回退 `TYPE_CONFIDENCE[type]`，对 `severity.score` 失败回退 `cluster_severity()`；`claude_code.py` 把 `create_subprocess_exec` 的 `OSError` 归一成 `could not start`；`_settings_file()` 固定 `Path.home()/.claude`，没有配置项。
5. 读页面与 API：`/steps/clusters` 的 DTO 没有 `algorithm` / `degraded` 字段；浏览器实拍显示 82% / 10.0 和“✓ 已完成 · 自进化有效”，没有任何 AI 降级提示。
6. 查网上“deploy 用户与运行用户分离”的常见做法：专用非登录服务账号是推荐做法（[SSD Nodes：Run services as an unprivileged user](https://www.ssdnodes.com/learn/least-privilege-users-vps)）；systemd 提供 `LoadCredential=`、`DynamicUser=`、`StateDirectory=`、`ConfigurationDirectory=` 等机制（[systemd.exec 官方文档](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)）；系统级 service 的 HOME/PATH 坑（[华为云：systemd 服务里的 HOME 是空的](https://bbs.huaweicloud.com/blogs/522224)）。
7. 读 Claude Code 官方环境变量：`CLAUDE_CONFIG_DIR` 可覆盖 `~/.claude`，settings/session/plugins 都从该目录读（[Claude Code env-vars](https://code.claude.com/docs/en/env-vars)）；`--no-session-persistence` 已用于 analyze；#488 已决定 edit 单发、reject 即结束该轮，`EditRequest` 没有 session_id，`_edit_argv` 却仍保留会话，`EditResult.session_id` 也没有调用方消费——这是 #492 为原 resume 循环留下的遗留。
8. 对比方案：① 服务用户专属 HOME（`Environment=HOME` + `StateDirectory`）能工作，但建 `/home/harness`/chown 需要 root/bootstrap；② 共享配置目录 + 组/ACL + 可配置 settings 路径能工作，但 ACL/属组依赖服务器是否装 `setfacl` 或一次 root 初始化；③ systemd `LoadCredential` 最安全，但要 root 改 unit/放凭据，不是纯流水线；④ 让服务直接用 deploy 跑最简单，但违背最小权限，不推荐。

### 结论

- 不是代码还在打桩：`provider=claude-code`、`algorithm=hybrid-lexical-llm-v1`，真实子类确实被调用了 3 次。
- 直接原因是 CLI/settings 对 harness 不可见；结构原因是“用户级资产”没有服务级化、职责无人认领；结果原因是静默降级 + 页面不暴露。
- 两个用户是正常的，且应保留；问题不是用户分离，而是把 CLI 当成了 deploy 的私有文件。
- 只补 Secret 不够；只改文档也不够。真正根治要同时做到：harness 可执行稳定路径的 CLI；harness 能读 settings/凭据；真实模式下失败显式失败、不落兜底。
- **可以纯流水线完成**：`CLAUDE_CONFIG_DIR` + 共享 settings（0644，不含密钥）+ `ANTHROPIC_API_KEY`（复用现有 `CLAUDE_CODE_API_KEY`，写入 0600 `.env`）+ stable `current` 软链；再给 edit 加 `--no-session-persistence`（#488 已是单发），就基本不需要 ACL/root。若 2.1.323 的 `--bare` 不认 `CLAUDE_CONFIG_DIR`，再补一个 `HE_AI_AGENT_CLAUDE_SETTINGS` 小改动，仍由流水线部署。

### 我对方案的要求

- **不要 fake**：`AI_AGENT_PROVIDER` 不是 `fake`（含默认 `claude-code`）时，聚类 AI 失败必须让 run 显式失败，不得落兜底 confidence/severity，不得显示“自进化有效”。
- **直接解决根因**：不要只补 Secret、只改文档或只加提示；要解决 harness 访问 CLI/settings 的问题，并把失败语义改对。
- **优先纯流水线**：能在 Deploy 流水线里完成，就不要人工上服务器；如果必须 root/手工，明确最小步骤、原因和可回退方式。
- **可验证**：真实 run 的 `ai_agent_call` 为 `outcome=ok`、tokens>0、model 非 unknown，`clusters_created.payload.degraded` 不出现；页面不再对失败结果展示“自进化有效”。
- **保持安全边界**：保留 deploy/harness 两个用户和最小权限；不接受 0777、服务直接用 deploy 跑、或把密钥写进 settings/仓库。

### 最推荐的根治方案

1. **保留两个用户**：deploy 只负责发布/重启；harness 只跑服务；不共享 home，不把服务降级成 deploy。
2. **把 Claude Code 变成服务级资产（纯流水线）**：
   - `deploy/install-claude-code.py` 在现有版本目录旁创建稳定 `current` 软链；以 deploy 写共享 `settings.json` 到 `/opt/harness/shared/claude-code/config`（0644，不含 `apiKeyHelper`/密钥；保留 model、ANTHROPIC_BASE_URL、别名、MiniMax 参数）。
   - Deploy 往 0600 的 `/opt/harness/shared/.env` 注入 `CLAUDE_CONFIG_DIR=/opt/harness/shared/claude-code/config`、`ANTHROPIC_API_KEY`（值复用 `CLAUDE_CODE_API_KEY`，走既有 base64/stdin 通道）、`HE_AI_AGENT_CLAUDE_BIN=/opt/harness/shared/claude-code/current/usr/bin/claude`；不需要新建 Secret。
   - Claude Code 从 `CLAUDE_CONFIG_DIR` 读 settings，从环境变量读 key；harness 不需要读 deploy 的 home，也不需要 chown。
   - 给 `_edit_argv` 加 `--no-session-persistence`（#488 已单发），去掉遗留的 session 写入；这样共享 config 可以只读，连 ACL 都不需要（若 CLI 仍写其他缓存，用一次 smoke 确认，再按需 `setfacl -m u:harness:rwx` 或加可写 state 子目录）。
   - 部署后做一次真实 `claude -p`/run 冒烟；若 `--bare` 不认 `CLAUDE_CONFIG_DIR`，加 `HE_AI_AGENT_CLAUDE_SETTINGS` 配置（provider `_settings_file()` 支持显式路径）作为兜底，仍由流水线部署。
3. **真实模式不降级（本 issue 核心）**：新增 `HE_AI_AGENT_FAILURE_POLICY=strict|degrade`，默认按 provider 推导（`fake` → `degrade`，其余 → `strict`）；strict 下 `cluster_llm` 抛 `ClusterAIFailure`，`prepare` 不写兜底簇，engine 把 run 标为 failed/blocked 并记录可诊断错误；degrade 仅显式使用。
4. **可观测性**：`/steps/clusters` 暴露 algorithm/failurePolicy/degraded/failure reason；UI 不再对失败结果显示“自进化有效”；Deploy preflight 检查 `current` 可执行、settings 可读，失败在切换 `current` 前中止。
5. **备选（需要 root/一次性初始化）**：③ `LoadCredential`（最安全，但要 root 改 unit/放凭据）；① 服务用户专属 HOME（要 root 建 `/home/harness` 或 chown）；② 的 ACL 变体（`setfacl` 不存在时不可用）。这些不是首选，因为不满足“纯流水线”的要求。

## 目标

- 定义“真实模式”：`AI_AGENT_PROVIDER` 不是 `fake`（包括默认 `claude-code`）时，聚类三层调用失败必须让本次 run 在聚类阶段显式失败，不得落库兜底 confidence/severity，也不得把 run 标记为有效或 accepted。
- 保留降级能力，但只用于 `fake` 或显式允许降级的配置：`HE_AI_AGENT_FAILURE_POLICY=strict|degrade`，默认 `strict`（provider 为 `fake` 时默认 `degrade`）；`degrade` 必须在 API/UI 上可见，不能伪装成正常结果。
- 失败可诊断：保留 `ai_agent_call` 的 task/provider/model/tokens/cost/latency/outcome，新增/复用失败事件记录脱敏后的错误类别与 stage；run 的 error/blocked 信息能直接指向 CLI 路径、settings 可读性或鉴权问题。
- 页面不再对降级/失败结果展示“自进化有效”：聚类步骤显示失败原因，run 状态与终评联动；不把 fake 评测分数当作真实模型参与的证据。
- 纯流水线修复部署前置：`CLAUDE_CONFIG_DIR` + 共享 settings + 环境变量 key + stable `current`；`HE_AI_AGENT_CLAUDE_BIN` 指向 harness 可执行的绝对路径；edit 改为 `--no-session-persistence`；Deploy 在切换 `current` 前做 preflight。

## 设计依据

- [07 §5.5.2](../../../plans/fullstack-design/07-backend-implementation.md)：三层聚类的审查/评分任务与三条降级路径；本 issue 修改的是“真实模式下是否允许降级”的契约，并补部署前置。
- [07 §5.5.1](../../../plans/fullstack-design/07-backend-implementation.md)：AI Agent provider 的父类契约与 `AI_AGENT_PROVIDER` 选择；strict/degrade 策略应落在这一层，而不是散落在业务分支。
- [06 §5.3](../../../plans/fullstack-design/06-database-design.md)：`confidence` / `severity` / `rank` 的持久化契约；strict 失败时不得写入兜底值，避免“零迁移”字段被错误数据污染。
- [2026-11-22 真实模型化设计 Note](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/feature/2026-11-22-evolution-real-ai-design.md)：降级“最坏情况等于今天的行为”的原始取舍；本 issue 记录在真实模式下该取舍不再成立，并补 deploy/harness 用户边界的根治。
- 外部参考：[systemd.exec](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)（LoadCredential/DynamicUser/StateDirectory/ConfigurationDirectory）、[SSD Nodes 专用服务账号](https://www.ssdnodes.com/learn/least-privilege-users-vps)、[systemd 服务 HOME/PATH 坑](https://bbs.huaweicloud.com/blogs/522224)、[Claude Code env-vars / CLAUDE_CONFIG_DIR](https://code.claude.com/docs/en/env-vars)。

## 实现内容

- **配置与策略解析**：在 `Settings` 增加 `ai_agent_failure_policy: Literal["strict", "degrade"]`（环境键 `HE_AI_AGENT_FAILURE_POLICY`，默认按 provider 推导：`fake` → `degrade`，其余 → `strict`）；未知值启动失败；`deploy/env.production.example` 与 `docs/deployment.md` 同步。
- **聚类失败传播**：`cluster_llm.enhance_clusters` 在 strict 模式下不再捕获后返回 fallback，而是抛出带 task 与脱敏原因的 `ClusterAIFailure`；`prepare._enhance_clusters` 让异常上抛；`prepare` 不调用 `replace_prepared_clusters` 写兜底簇，不产生“成功”的 `clusters_created`。
- **run/stage 语义**：engine 把聚类阶段失败映射为 `failed`（或现有 `blocked` 机制中与“需要人工/重试”匹配的状态），记录 stage error；保留已发生的 `ai_agent_call` 事件；不使用有误导性的 `degraded` 成功口径；重试仍走既有 run retry，不新增 turn 级循环。
- **纯流水线部署前置**：`deploy/install-claude-code.py` 写共享 `settings.json`（0644，无密钥）与 `current` 软链；`deploy.yml` 注入 `CLAUDE_CONFIG_DIR`、`ANTHROPIC_API_KEY`（复用 `CLAUDE_CODE_API_KEY`）、`HE_AI_AGENT_CLAUDE_BIN`；`_edit_argv` 加 `--no-session-persistence`；如需兜底，增加 `HE_AI_AGENT_CLAUDE_SETTINGS` 并让 provider `_settings_file()` 使用显式路径。
- **API/UI**：`/steps/clusters` 增加 algorithm/failurePolicy/degraded/failure reason；契约变更同步 `packages/contracts` 与生成类型；页面不再对失败结果展示“自进化有效”。
- **测试**：strict 模式下任一 task 失败 → run 失败且无兜底簇；fake/degrade 模式保持现有回退；CLI 的 ENOENT/EACCES/非零退出/超时分别映射到可诊断的失败；部署 preflight 的失败分支有断言；`CLAUDE_CONFIG_DIR`/共享 settings/`--no-session-persistence` 有单测或 smoke。

## 实施步骤

1. 定义 strict/degrade 配置与默认推导，补 Settings 校验、env 模板、部署注入与单测。
2. 改造 `cluster_llm` / `prepare` / engine 的失败传播与 run 状态；strict 失败不落库兜底值，degrade 仍可用但必须显式可见。
3. 落地纯流水线部署前置：共享 settings + `current` 软链 + `CLAUDE_CONFIG_DIR`/`ANTHROPIC_API_KEY`/`HE_AI_AGENT_CLAUDE_BIN` 注入；`_edit_argv` 加 `--no-session-persistence`。
4. 扩展 API/UI 的失败与降级展示，更新 contracts 并重新生成类型。
5. 部署后用一次真实 run 验证 `outcome=ok`、tokens>0、无降级；若 `CLAUDE_CONFIG_DIR` 不生效，补 `HE_AI_AGENT_CLAUDE_SETTINGS` 兜底并重试。
6. 补 strict/degrade/部署配置的测试与文档，更新 Agent Note；跑门禁。

## 依赖与交付边界

- 依赖：bugfix-15（provider 骨架与 Settings）、bugfix-17（真实 Claude Code 子类）、bugfix-19（三层聚类与现有降级）、bugfix-23（三键经 Secrets 注入）。
- 交付边界：本 issue 负责“真实模式不静默降级”的契约、API/UI 可见性、纯流水线部署前置（共享 settings/current/env key/no-session edit）；不在本 issue 内改 patch 生成（agent-edit）的语义、评测网关或 turn 生命周期。
- 生产 Secret 的值（模型 API key、CLI 绝对路径）不进入仓库；文档只写键名、语义与验证命令；`ANTHROPIC_API_KEY` 由 Deploy 从既有 `CLAUDE_CODE_API_KEY` 注入，不新增 Secret。

## 独立验证

```sh
pnpm test:api -- tests/test_clustering_three_layers.py
pnpm test:api -- tests/test_ai_agent_claude_code.py
pnpm test:gates
pnpm verify:flow
```

- strict 用例：mock provider 让 `cluster.review`/`cluster.score`/`severity.score` 分别失败，断言 run 在聚类阶段失败、没有 fallback 簇落库、没有“成功”的 `clusters_created`、错误信息包含 task 与脱敏原因。
- degrade 用例：provider=fake 或显式 `degrade`，断言现有词面/常量/公式回退与事件保持不变。
- 部署用例：preflight 在 harness 无法执行 CLI 或无法读取 settings 时让发布失败；`CLAUDE_CONFIG_DIR`/共享 settings/`--no-session-persistence` 的 argv/配置有断言；配置正确时通过。
- 生产验证：真实 run 的 `ai_agent_call` 为 `outcome=ok`、tokens>0、model 非 unknown；`clusters_created.payload.degraded` 不出现。

## 验收标准

- `AI_AGENT_PROVIDER=claude-code`（含默认值）且任一聚类 AI 调用失败：run 不进入“有效/accepted”，聚类阶段显式失败，数据库无兜底 confidence/severity 簇，页面不显示“自进化有效”，错误可定位到 CLI 路径/settings/鉴权。
- `AI_AGENT_PROVIDER=fake` 或显式 `HE_AI_AGENT_FAILURE_POLICY=degrade`：现有降级行为与测试保持不变。
- 生产按纯流水线方案配置后，真实 run 的 `ai_agent_call` 为 `outcome=ok`、tokens>0、model 非 unknown，`clusters_created.payload.degraded` 不出现，置信度不再恰好等于类目常量；不需要人工 SSH/root 步骤。
- Deploy 在 CLI/settings 不可用时于切换 `current` 前失败，不把坏配置带上线；`current`/共享 settings/环境变量 key 的路径稳定，CLI 升级不破坏 Secret。
- 单测、契约检查、`test:gates`、`verify:flow` 全绿。

## 门禁与 CI

- api-static / unit-tests-api / docs-flow；涉及契约时加 `pnpm contract:check`；涉及部署时加 deploy 相关测试与 `pnpm test:gates`。
- 提交与 PR 标题带 `(#N)`。

## 非目标

- 不在真实模式下保留“静默降级 + 正常结果”的兼容路径；不把 `degraded` 当作成功口径。
- 不改 `fake` provider 的确定性行为，也不删除 `degrade` 能力（它是离线/测试的显式选择）。
- 不把服务改成 deploy 用户运行，不设 0777，不把密钥写进 settings/仓库；不以扩大 root/sudo 权限作为默认方案。
- 不在本 issue 内实现 agent-edit 的 Settings 枚举放开、评测从 fake 切真实、或 turn 级自动重试。
