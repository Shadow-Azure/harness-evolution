# AI Agent Provider 骨架：契约、工厂、fake 与配置装配

[English](bugfix-ai-agent-provider-skeleton.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-15
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/app/config.py
  - apps/api/app/main.py
  - apps/api/tests/**
  - .agents/**
adr:
  - ../../notes/proposed/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 490
  url: https://github.com/Shadow-Azure/harness-evolution/issues/490
```

## 背景

自进化真实模型化的设计已合入（#487）：模型出站调用统一收口到 `third_party_api/ai_agent` 的「父类契约 + 子类 + 工厂」。本 issue 是实施路线的第一步——只落地骨架，不含任何真实后端与业务接入。

## 目标

- 新增 `apps/api/app/third_party_api/ai_agent/` 包：`contracts.py`（AnalysisRequest/AnalysisResult、EditRequest/EditResult、AgentUsage、ProviderHealth、AgentProviderError）、`base.py`（`AIAgentProvider` ABC）、`factory.py`（注册表 + `build_agent_provider(settings)`）、`fake.py`（确定性 `FakeAIAgentProvider`）。
- `Settings` 只新增两项：`ai_agent_provider`（`AliasChoices("AI_AGENT_PROVIDER","HE_AI_AGENT_PROVIDER")`，默认 `claude-code`，校验器限定注册表内值）与 `ai_agent_claude_bin`（默认 `~/.local/bin/claude`，M15 部署产物路径，零配置可跑）。**不加其他子配置项**——超时（analyze 300s / edit 1800s）与权限模式（`dontAsk`）用代码常量，避免过度设计。
- `main.py` 装配：构建 provider 单例挂 `app.state`，lifespan 启动时 `health_check` 记事件。
- 单测覆盖：工厂选择、未知值启动红、fake 的 analyze/edit_workspace 确定性行为、错误归一化字段。

## 设计依据

- [07 §5.5.1](../../../plans/fullstack-design/07-backend-implementation.md)：父类三能力面（analyze/edit_workspace/health_check）、归一化返回字段、工厂与 `AI_AGENT_PROVIDER` 选择语义。
- [04 §5.1](../../../plans/fullstack-design/04-backend-architecture.md)：`ai_agent` 是模型出站唯一接缝，非统一 Provider 复活。
- 仓库先例：`PatchSource`（Protocol+工厂+env 兜底）、`GitPushProvider`（ABC+注册表工厂）、`FakeEvalGateway`（fake 先行）。

## 实现内容

- `contracts.py` 数据类全部 frozen dataclass，docstring 对齐仓库导出注释规范；`AgentProviderError(message, *, retryable, provider_id, detail)`。
- `factory.py` 模块级注册表；本 issue 仅注册 `fake`，`claude-code` 键留给 bugfix-17（未注册键被 Settings 校验拒绝前可临时允许 claude-code 缺席或以显式占位抛 `NotImplementedError`，以测试方便为准）。
- `fake.py`：analyze 按 task 键返回固定结构并过调用方 schema；edit_workspace 返回固定 EditResult。
- 装配不接任何 service 消费方——业务接入在 bugfix-18/19/21。

## 实施步骤

1. 建包与四模块；Settings 字段与校验器。
2. main.py 装配 + lifespan health 事件。
3. 单测（fake 全程，不触网）。
4. 门禁：`pnpm lint:api`、`pnpm typecheck:api`、`pnpm test:api`、`pnpm verify:flow`。

## 依赖与交付边界

- 依赖：无（整条实施链的根）。
- 交付边界：只加 `ai_agent` 包、Settings、装配与测试；不改 service/evolution 业务代码；不实现真实子类。

## 独立验证

```sh
pnpm test:api -- tests/test_ai_agent_factory.py
AI_AGENT_PROVIDER=unknown python -c "from app.config import Settings; Settings(_env_file=None)"
```

- 测试全绿；第二条抛出含 `unknown AI agent provider` 的校验错误（启动即红）。

## 验收标准

- 包四模块齐；工厂按 env 选择；未知值启动红有测试钉住。
- `FakeAIAgentProvider` 可被业务层无感使用（后续 issue 单测全走它）。
- `app.state` 可取到 provider；lifespan 记 health 事件。
- CI 全绿；覆盖率不低于既有红线。

## 门禁与 CI

- api-static / unit-tests-api / docs-flow（test:gates、verify:docs）。
- 提交与 PR 标题带 `(#N)`；scope 覆盖 `ai_agent/**`、`config.py`、`main.py`、tests、`.agents/**`。

## 非目标

- 不实现 Claude Code 真实调用（bugfix-17）与 submission 通道（bugfix-16）。
- 不接业务环节（bugfix-18/19/21）。
- 不做 OpenCode/model 子类。
