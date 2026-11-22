# Claude Code 子类：无头调用、进程管理与用量采集

[English](bugfix-claude-code-provider.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-17
milestone: bugfix
depends:
  - bugfix-15
  - bugfix-16
priority: P2
status: in-progress
scope:
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/app/config.py
  - apps/api/tests/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/proposed/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 492
  url: https://github.com/Shadow-Azure/harness-evolution/issues/492
```

## 背景

骨架（bugfix-15）与提交通道（bugfix-16）就绪后，需要第一个真实子类：复用生产部署的 `claude` CLI（M15）完成 `analyze` 与 `edit_workspace` 的真实调用。本 issue 只做子类本身，业务环节接入在 bugfix-19/21。

## 目标

- 新增 `third_party_api/ai_agent/claude_code.py`：`ClaudeCodeProvider`，注册 `claude-code`，实现三个抽象方法。
- **analyze 路径**：`claude --bare -p <prompt> --output-format json --permission-mode dontAsk --allowed-tools "Write(./result.json5)" --settings <部署 settings>`，结论经 submission 通道收货；校验失败 `--resume <session_id>` 带反馈重试 ≤1 轮。
- **edit_workspace 路径**：只读工具 + `Write(./.harness-evolution/edits.json5)`（本轮只把 EditPlan 提交与收货跑通；确定性应用器在 bugfix-20）。
- **进程管理**：`create_subprocess_exec` + `start_new_session=True` + `asyncio.wait_for`；超时/取消先 SIGINT 后 `killpg(SIGKILL)`；退出码 143 识别为「已取消」而非失败。
- **用量采集**：result 的 `total_cost_usd` / `model_usage` / `session_id` 映射进 `AgentUsage`。
- 不实现 `--json-schema` 快路径：submission 通道（自建字面量收货）是默认且唯一路径，避免两套通路与额外配置开关。

## 设计依据

- [07 §5.5.1](../../../plans/fullstack-design/07-backend-implementation.md)：子类进程管理姿势（复用 git workspace 模式）、凭据零感知、fake 先行边界。
- [07 §5.5.3](../../../plans/fullstack-design/07-backend-implementation.md)：无头调用规格与 `--bare`/`--settings` 决策、SIGINT 信号语义。

## 实现内容

- 进程封装可注入（mock 子进程单测：超时杀组、非零退出、143 取消、stream-json 末行 result）。
- 特性探测用 `system/init.capabilities`，不用版本号比较。
- analyze 调用加 `--no-session-persistence`；edit 路径保留会话（`--resume` 供迭代）。
- e2e 冒烟（env 开关切真 CLI，串行 lane，可跳过无 CLI 环境）。

## 实施步骤

1. 实现 claude_code.py 与注册。
2. mock 子进程单测矩阵。
3. e2e 冒烟（可选开关）。
4. 门禁：`pnpm lint:api`、`pnpm typecheck:api`、`pnpm test:api`、`pnpm verify:flow`。

## 依赖与交付边界

- 依赖：bugfix-15（骨架）、bugfix-16（submission 收货）。
- 交付边界：只实现子类与测试；不接聚类/patch 业务；edit_workspace 的确定性应用在 bugfix-20。

## 独立验证

```sh
pnpm test:api -- tests/test_ai_agent_claude_code.py
```

- mock 矩阵全绿：正常、超时、非零退出、143 取消、resume 回喂重试。

## 验收标准

- `AI_AGENT_PROVIDER=claude-code` 时工厂产出真实子类；analyze 产物过调用方 schema。
- 超时与取消路径杀进程组且归类正确；usage/session_id 字段完整。
- submission 通道为默认且唯一路径；不引入 native 快路径开关。
- CI 全绿；单测不触网。

## 门禁与 CI

- api-static / unit-tests-api / docs-flow / e2e（冒烟开关）。
- 提交与 PR 标题带 `(#N)`。

## 非目标

- 不接聚类/评分/patch 业务（bugfix-19/21）。
- 不实现 edits.py 应用器（bugfix-20）。
- 不做 OpenCode/model 子类。
