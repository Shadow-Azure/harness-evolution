# AI Agent 出站层

[English](ai-agent.en.md) | 中文

自进化的审查、评分与 patch 生成经统一出站层调用模型；安装与模型配置见 [claude-code.md](claude-code.md)。

## 分层

- `apps/api/app/third_party_api/ai_agent/` 是唯一出站缝：业务服务只调 `build_agent_provider`，不 import 厂商模块，也不按后端名分支。
- `AIAgentProvider` 只定契约，两个能力面是 `analyze`（结构化分析）与 `edit_workspace`（提交编辑计划）。
- 工厂按 `AI_AGENT_PROVIDER` 选注册表里的子类：`claude-code` 是默认项，`fake` 给单测与 CI 确定性结果；新增后端只加一个子类与注册项。

## Analyze 任务

- 任务键恰好三个：`cluster.review` 合并草稿并命名，`cluster.score` 给簇置信度，`severity.score` 给严重度。
- 有草稿时每次运行恰好 3 次有界调用（无草稿时 0 次）；输入是草稿摘要与代表样本，成员列表由代码持有，调用量与归因报告总量 N 解耦。
- 任一调用失败或输出违反契约时，该任务降级为确定性词法值或公式值，并另记一条 `degraded` warn 事件（`task` 与 `reason`）。

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

- `outcome` 取 `ok`、`degraded` 或 `error`；`submissionParsedBy` 是最后一批解析档位（即使文档随后校验失败），无提交时为 null；`submissionRepaired` 表示最后一批经 repair 档，成功与否看 `outcome`。
- 解析失败率 = `submissionParseFailures` / `submissionRounds`（`submissionRounds=0` 时比率不适用）；`feedbackRetries` 是回喂重试次数。
- analyze 事件落 stage `cluster` 第 5 步（`step_index=4`），agent-edit 事件落 stage `candidate` 第 6 步（`step_index=5`）。
- 失败调用在已解析 CLI 结果后保留 usage 与 latency；解析前的进程级失败记 0 与 unknown。

## 配置

| 设置 | 默认 | 说明 |
|---|---|---|
| `AI_AGENT_PROVIDER` | `claude-code` | 选择注册子类；`fake` 供确定性测试 |
| `HE_AI_AGENT_CLAUDE_BIN` | `~/.local/bin/claude` | Claude Code CLI 路径 |
| `HE_PATCH_SOURCE_MODE` | `placeholder` | 可选 `minimal-config`、`agent-edit`；`agent-edit` 需已配置的 provider |

模型凭据由部署写入 `~/.claude`，服务进程不读取。前端观测面板是明确非目标。
