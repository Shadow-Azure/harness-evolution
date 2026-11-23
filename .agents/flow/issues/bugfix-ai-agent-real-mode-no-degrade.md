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
  - ../../notes/proposed/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 521
  url: https://github.com/Shadow-Azure/harness-evolution/issues/521
```

## 背景

用户在生产 run `01M834EBAY3C9BB3TM8V85VHQN`（2026-11-23 10:40，目标 `codespec-subagent-driven-development`）里看到聚类置信度仍是 `0.82`、严重度仍是 `10.0`，怀疑聚类和置信度环节还在走打桩代码。实际排查发现：代码已经接入真实 provider，但三次真实调用全部失败，系统按现有设计静默降级成确定性兜底值，页面仍显示“✓ 已完成 · 自进化有效”。用户明确要求：**在有配置说不要 fake 的情况下，不要降级**。

### 分析过程

1. 读生产 run 的 `events`：seq 6/8/10 分别是 `cluster.review`、`cluster.score`、`severity.score` 三次 `ai_agent_call`，provider 都是 `claude-code`，outcome 都是 `error`，耗时 7–8ms，`model=unknown`，`inputTokens=0`、`outputTokens=0`、`costUsd=0`；seq 7/9/11 是三条 `degraded`，原因统一为 `AgentProviderError: claude-code analysis call could not start`；seq 12 的 `clusters_created` 仍落 `algorithm=hybrid-lexical-llm-v1`，但 `degraded=[cluster.review, cluster.score, severity.score]`。
2. 读部署日志：最近两次成功的 Deploy（`45101610757` / `45099843286`）都显示 `claude-code 2.1.323` 已安装、`settings: /home/***/.claude/settings.json`，但 `AI Agent Secret：0/3 已写入、其余已移除`；`CLAUDE_CODE_MODEL`、`CLAUDE_CODE_API_KEY`、`CLAUDE_CODE_BASE_URL` 三个 Secret 已配置。
3. 读配置与部署拓扑：`Settings` 默认 `ai_agent_provider=claude-code`、`ai_agent_claude_bin=~/.local/bin/claude`；服务以 `harness` 用户运行且 `useradd --system --no-create-home`，默认路径展开成 `/home/harness/.local/bin/claude`，不存在；M15 把 CLI 和 `~/.claude` 装在 `deploy` 用户下，`harness` 读不到。`claude_code.py` 把 `create_subprocess_exec` 的 `OSError` 归一成 `could not start`，所以 7–8ms 的失败是“进程没起来”，不是 API key 鉴权失败。
4. 读聚类代码：`prepare.py` 在 `agent is None` 时走词面路径，否则走 `_enhance_clusters`；`cluster_llm.py` 对 `cluster.review` 失败回退词面草稿，对 `cluster.score` 失败回退 `TYPE_CONFIDENCE[type]`，对 `severity.score` 失败回退 `cluster_severity()`；三条路径都只记 `degraded` 事件，不阻塞 run，也不改 `hybrid-lexical-llm-v1` 标识。
5. 读页面与 API：`/steps/clusters` 的 DTO 没有 `algorithm` / `degraded` 字段，页面看不到降级；run 终态仍由 fake 评测的 85 > 80 推出“自进化有效”。也就是说，真实调用失败被两层“看起来正常”掩盖了。

### 结论

- 不是代码还在打桩：`provider=claude-code`、`algorithm=hybrid-lexical-llm-v1`，真实子类确实被调用了 3 次。
- 直接原因是 CLI 对 `harness` 不可见：`AI_AGENT_PROVIDER`、`HE_AI_AGENT_CLAUDE_BIN`、`HE_PATCH_SOURCE_MODE` 三个 Secret 未配置（0/3），服务回退默认 `~/.local/bin/claude`，在 harness 下不存在；即使把绝对路径填上，CLI 的 settings/凭据仍在 deploy 的 0700 home 下，harness 读不到。
- 结构原因是“静默降级”：现有设计把任何真实调用失败都折叠成确定性兜底，只写一条 warn 事件；这适合 `fake`/离线模式，但不适合“配置为真实 AI”的情况，因为它会把故障伪装成正常的 0.82/10.0，用户无法从结果上判断模型是否参与。
- 修复不能只补 Secret：需要同时解决“harness 可执行 CLI + harness 可读 settings/凭据”，并且把真实模式下的失败语义改成显式失败；否则下次遇到超时、鉴权失败、CLI 升级等仍会静默回退。

## 目标

- 定义“真实模式”：`AI_AGENT_PROVIDER` 不是 `fake`（包括默认 `claude-code`）时，聚类三层调用失败必须让本次 run 在聚类阶段显式失败，不得落库兜底 confidence/severity，也不得把 run 标记为有效或 accepted。
- 保留降级能力，但只用于 `fake` 或显式允许降级的配置：建议新增 `HE_AI_AGENT_FAILURE_POLICY=strict|degrade`，默认 `strict`（provider 为 `fake` 时默认 `degrade`）；`degrade` 必须在 API/UI 上可见，不能伪装成正常结果。
- 失败可诊断：保留 `ai_agent_call` 的 task/provider/model/tokens/cost/latency/outcome，新增/复用失败事件记录脱敏后的错误类别与 stage；run 的 error/blocked 信息能直接指向 CLI 路径、settings 可读性或鉴权问题。
- 页面不再对降级/失败结果展示“自进化有效”：聚类步骤显示失败原因，run 状态与终评联动；不把 fake 评测分数当作真实模型参与的证据。
- 修复部署前置：`HE_AI_AGENT_CLAUDE_BIN` 指向 harness 可执行的稳定绝对路径；CLI settings/凭据对 harness 可读（或改用环境变量认证）；Deploy 在切换 `current` 前做一次以 harness 身份执行的 preflight。

## 设计依据

- [07 §5.5.2](../../../plans/fullstack-design/07-backend-implementation.md)：三层聚类的审查/评分任务与三条降级路径；本 issue 修改的是“真实模式下是否允许降级”的契约。
- [07 §5.5.1](../../../plans/fullstack-design/07-backend-implementation.md)：AI Agent provider 的父类契约与 `AI_AGENT_PROVIDER` 选择；strict/degrade 策略应落在这一层，而不是散落在业务分支。
- [06 §5.3](../../../plans/fullstack-design/06-database-design.md)：`confidence` / `severity` / `rank` 的持久化契约；strict 失败时不得写入兜底值，避免“零迁移”字段被错误数据污染。
- [2026-11-22 真实模型化设计 Note](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/proposed/feature/2026-11-22-evolution-real-ai-design.md)：降级“最坏情况等于今天的行为”的原始取舍；本 issue 记录在真实模式下该取舍不再成立。

## 实现内容

- **配置与策略解析**：在 `Settings` 增加 `ai_agent_failure_policy: Literal["strict", "degrade"]`（环境键建议 `HE_AI_AGENT_FAILURE_POLICY`，默认按 provider 推导：`fake` → `degrade`，其余 → `strict`）；未知值启动失败；`deploy/env.production.example` 与 `docs/deployment.md` 同步。
- **聚类失败传播**：`cluster_llm.enhance_clusters` 在 strict 模式下不再捕获后返回 fallback，而是抛出带 task 与脱敏原因的 `ClusterAIFailure`；`prepare._enhance_clusters` 让异常上抛；`prepare` 不调用 `replace_prepared_clusters` 写兜底簇，不产生“成功”的 `clusters_created`。
- **run/stage 语义**：engine 把聚类阶段失败映射为 `failed`（或现有 `blocked` 机制中与“需要人工/重试”匹配的状态），记录 stage error；保留已发生的 `ai_agent_call` 事件；不使用有误导性的 `degraded` 成功口径；重试仍走既有 run retry，不新增 round 级循环。
- **API/UI**：`/steps/clusters` 增加失败/降级信息（至少 algorithm、failurePolicy、degraded/failure reason）；聚类步骤与 run 终评不再对失败结果展示“自进化有效”；契约变更同步 `packages/contracts` 与生成类型。
- **部署前置**：Deploy 产出稳定的 `/opt/harness/shared/claude-code/current/usr/bin/claude` 软链；把 settings/凭据写到 harness 可读的共享路径（或支持通过 `ANTHROPIC_API_KEY`/`ANTHROPIC_BASE_URL` 环境变量认证）；注入 `HE_AI_AGENT_CLAUDE_BIN`（以及可选的 `HE_AI_AGENT_CLAUDE_SETTINGS`）；在切换 `current` 前以 harness 身份执行 `claude --version` 与 settings 可读性检查，失败即中止发布而不是上线后静默降级。
- **测试**：strict 模式下任一 task 失败 → run 失败且无兜底簇；fake/degrade 模式保持现有回退；CLI 的 ENOENT/EACCES/非零退出/超时分别映射到可诊断的失败；部署 preflight 的失败分支有断言；API/UI 的失败态有契约测试。

## 实施步骤

1. 定义 strict/degrade 配置与默认推导，补 Settings 校验、env 模板、部署注入与单测。
2. 改造 `cluster_llm` / `prepare` / engine 的失败传播与 run 状态；strict 失败不落库兜底值，degrade 仍可用但必须显式可见。
3. 扩展 API/UI 的失败与降级展示，更新 contracts 并重新生成类型。
4. 落地部署前置：稳定路径、harness 可读 settings/凭据、preflight 与失败中止。
5. 补 strict/degrade/部署配置的测试与文档，更新 Agent Note；跑门禁。
6. 在生产配置好 `AI_AGENT_PROVIDER`、`HE_AI_AGENT_CLAUDE_BIN`、settings/凭据后，用一次真实 run 验证 `outcome=ok`、tokens>0、无降级。

## 依赖与交付边界

- 依赖：bugfix-15（provider 骨架与 Settings）、bugfix-17（真实 Claude Code 子类）、bugfix-19（三层聚类与现有降级）、bugfix-23（三键经 Secrets 注入）。
- 交付边界：本 issue 负责“真实模式不静默降级”的契约、API/UI 可见性与部署前置的代码/配置；不在本 issue 内改 patch 生成（agent-edit）、评测网关或 round 生命周期。
- 生产 Secret 的值（模型 API key、CLI 绝对路径）不进入仓库；文档只写键名、语义与验证命令。

## 独立验证

```sh
pnpm test:api -- tests/test_clustering_three_layers.py
pnpm test:api -- tests/test_ai_agent_claude_code.py
pnpm test:gates
pnpm verify:flow
```

- strict 用例：mock provider 让 `cluster.review`/`cluster.score`/`severity.score` 分别失败，断言 run 在聚类阶段失败、没有 fallback 簇落库、没有“成功”的 `clusters_created`、错误信息包含 task 与脱敏原因。
- degrade 用例：provider=fake 或显式 `degrade`，断言现有词面/常量/公式回退与事件保持不变。
- 部署用例：preflight 在 harness 无法执行 CLI 或无法读取 settings 时让发布失败；配置正确时通过。

## 验收标准

- `AI_AGENT_PROVIDER=claude-code`（含默认值）且任一聚类 AI 调用失败：run 不进入“有效/accepted”，聚类阶段显式失败，数据库无兜底 confidence/severity 簇，页面不显示“自进化有效”，错误可定位到 CLI 路径/settings/鉴权。
- `AI_AGENT_PROVIDER=fake` 或显式 `HE_AI_AGENT_FAILURE_POLICY=degrade`：现有降级行为与测试保持不变。
- 生产按修复方案配置后，真实 run 的 `ai_agent_call` 为 `outcome=ok`、tokens>0、model 非 unknown，`clusters_created.payload.degraded` 不出现，置信度不再恰好等于类目常量。
- Deploy 在 CLI/settings 不可用时于切换 `current` 前失败，不把坏配置带上线。
- 单测、契约检查、`test:gates`、`verify:flow` 全绿。

## 门禁与 CI

- api-static / unit-tests-api / docs-flow；涉及契约时加 `pnpm contract:check`；涉及部署时加 deploy 相关测试与 `pnpm test:gates`。
- 提交与 PR 标题带 `(#N)`。

## 非目标

- 不在真实模式下保留“静默降级 + 正常结果”的兼容路径；不把 `degraded` 当作成功口径。
- 不改 `fake` provider 的确定性行为，也不删除 `degrade` 能力（它是离线/测试的显式选择）。
- 不在本 issue 内实现 `agent-edit` 的 Settings 枚举放开、评测从 fake 切真实、或 round 级自动重试。
- 不把生产 Secret 值写入仓库、文档或 issue；不新增绕过 harness 权限的 root 方案。
