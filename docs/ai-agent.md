# AI Agent 出站层

[English](ai-agent.en.md) | 中文

自进化的审查、评分与 patch 生成经统一出站层调用模型；安装与模型配置见 [claude-code.md](claude-code.md)。

## 分层

- `apps/api/app/third_party_api/ai_agent/` 是唯一出站缝：业务服务只调 `build_agent_provider`，不 import 厂商模块，也不按后端名分支。
- `AIAgentProvider` 只定契约：`analyze`（结构化分析）、`edit_workspace`（提交编辑计划）与可选技能面 `stage_skill`/`run_skill`（归因随 provider 一起切换）。子类用 `capabilities` 显式声明能力面（`analyze`/`edit`/`skill`），未声明的旧子类仍按 `run_skill` 覆盖推导；`ProviderHealth.auth`（`ok`/`missing`/`unknown`）与 preflight 能力行让鉴权与二进制可用性可枚举。
- 工厂按 `AI_AGENT_PROVIDER` 选注册表里的子类，经 `from_settings` 装配：`claude-code` 是默认项，`fake` 给单测与 CI 确定性结果。换后端 = 一个子类 + 一个注册项：技能后端在 `stage_skill` 把平台中立布局 `work/skills/<name>/` 适配成自己的形态并返回原生前缀（Claude 建 `.claude/skills/<name>` 软链并返回 `/{name} `，通用后端空串零适配），配置在 `from_settings` 读 `HE_AI_AGENT_BIN`/`HE_AI_AGENT_SETTINGS`（新名优先，未设回落旧名）；服务层与业务代码零改动。

## Analyze 任务

- 任务键恰好三个：`cluster.review` 合并草稿并命名，`cluster.score` 给簇置信度，`severity.score` 给严重度。
- 有草稿时每次运行恰好 3 次有界调用（无草稿时 0 次）；输入是草稿摘要与代表样本，成员列表由代码持有，调用量与归因报告总量 N 解耦。
- 失败策略由 `HE_AI_AGENT_FAILURE_POLICY` 决定，默认按 provider 推导（`fake` → `degrade`，其余 → `strict`）。`strict` 下任务失败先记 `ai_agent_call(outcome=error)`，再抛带 `task` 与脱敏原因的 `ClusterAIFailure`，run 在聚类阶段失败，不落兜底值、不写成功 `clusters_created`；`degrade` 仅用于 `fake` 或显式配置，回退确定性值并记 `degraded`。

## 提交通道

Agent 每轮只写一个 `result.json5`；收货走确定性阶梯 strict JSON → JSON5 → json-repair，随后交给 Pydantic 校验。校验失败时回喂具体字段与约束，`analyze` 恰好一次有界重试；`edit`（任务键 `agent.edit`）不重试。契约与防线见 [`plans/fullstack-design/07-backend-implementation.md`](../plans/fullstack-design/07-backend-implementation.md) §5.5.1–§5.5.4。

## Edit 与 patch

`agent-edit` patch source 向 provider 收一份 EditPlan，在临时镜像上确定性应用，只写回被改动的文件；candidate commit 记录真实 `git diff`。评测 reject 结束该轮，不自动重试。

## 观测事件

每次出站调用记一条 `ai_agent_call` run 事件，payload 字段为：

```text
task provider model inputTokens outputTokens totalTokens costUsd latencyMs outcome
sessionId attempts feedbackRetries submissionRounds submissionParsedBy submissionRepaired
submissionParseFailures submissionValidationFailures
```

- `outcome` 取 `ok`、`degraded` 或 `error`；`submissionParsedBy` 是最后一轮的解析档位（即使文档随后校验失败），无提交时为 null；`submissionRepaired` 表示最后一轮经 repair 档，成功与否看 `outcome`。
- 解析失败率 = `submissionParseFailures` / `submissionRounds`（`submissionRounds=0` 时比率不适用）；`feedbackRetries` 是回喂重试次数。
- analyze 事件落 stage `cluster` 第 5 步（`step_index=4`），agent-edit 事件落 stage `candidate` 第 6 步（`step_index=5`）。
- 失败调用在已解析 CLI 结果后保留 usage 与 latency；解析前的进程级失败记 0 与 unknown。
- `/steps/clusters` 暴露 `algorithm`/`failurePolicy`/`degraded`/`failure`；页面显示回退任务或严格失败原因，失败 run 不再展示“自进化有效”。

## 配置

| 设置 | 默认 | 说明 |
|---|---|---|
| `AI_AGENT_PROVIDER` | `claude-code` | 选择注册子类；`fake` 供确定性测试 |
| `HE_AI_AGENT_BIN` / `HE_AI_AGENT_SETTINGS` | 空 | 通用后端配置入口；新名优先，未设时回落 `HE_AI_AGENT_CLAUDE_*` |
| `HE_AI_AGENT_CLAUDE_BIN` | `~/.local/bin/claude` | Claude Code CLI 路径（deprecated 别名）；部署注入稳定 `current` 路径 |
| `HE_AI_AGENT_CLAUDE_SETTINGS` | 空 | 显式 settings 路径（deprecated 别名）；空时用 `CLAUDE_CONFIG_DIR`/`~/.claude` |
| `HE_AI_AGENT_FAILURE_POLICY` | 按 provider | `strict`（真实默认）/`degrade`（`fake` 默认）；未知值启动失败 |
| `HE_PATCH_SOURCE_MODE` | `placeholder` | 可选 `minimal-config`、`agent-edit`；`agent-edit` 需已配置的 provider |

模型凭据由部署写入 0600 `.env` 与共享 settings；服务只把环境传给 CLI，不读取/打印/落库。前端观测面板是明确非目标。
