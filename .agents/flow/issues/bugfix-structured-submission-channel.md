# 结构化提交通道 submission.py：JSON5 收货、校验与回喂

[English](bugfix-structured-submission-channel.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-16
milestone: bugfix
depends:
  - bugfix-15
priority: P2
status: done
scope:
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/pyproject.toml
  - apps/api/tests/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 495
  url: https://github.com/Shadow-Azure/harness-evolution/issues/495
```

## 背景

设计（#487）决定 `analyze` 的结构化收货不依赖任何 CLI 内部机制：agent 写宽松字面量文件、我们的确定性解析器收货。该通道是 provider 层公共组件，被 claude-code/opencode 等所有 CLI 子类共享，是六层 JSON 可靠性防线的第 1 层。

## 目标

- 新增 `third_party_api/ai_agent/submission.py`：`StructuredSubmission` 组件，三方法契约——`prepare(task_key, output_schema) -> SubmissionPrep`（建一次性任务目录、落 schema.json、生成指令片段与唯一工具白名单 `Write(./result.json5)`）、`collect(prep, validate) -> SubmissionOutcome`（读 result.json5 → JSON5 宽容解析 → 失败走 json-repair 抢救 → 规范化 → 调用方 `model_validate`）、`feedback_prompt(outcome) -> str`（把具体错误拼成可定位的回喂文案）。
- `SubmissionOutcome` 三态终局：`ok / invalid / missing`，携带 `parse_error` 与 `validation_error` 两类错误文本。
- 新增纯 Python 依赖 `json5`（pyproject）与 `json-repair`（兜底）。
- 单测：JSON5 各类宽容格式（注释/尾逗号/单引号/裸键）、修复兜底、三态终局、反馈文案含字段与约束、任务目录一次性。

## 设计依据

- [07 §5.5.3](../../../plans/fullstack-design/07-backend-implementation.md)：通道机制、六层防线、「用 JS 生成 JSON」的价值提炼（字面量容错 + 确定性序列化，不执行模型代码）。
- Agent Note（adr）：自建通道 vs `--json-schema` 的取舍记录。

## 实现内容

- `prepare` 的任务目录按调用隔离（uuid/任务键派生），不复用；`prompt_addendum` 说明「结论写进 result.json5（JSON5 宽松格式），形状见 schema.json」。
- `collect` 解析顺序：标准 JSON → JSON5 → json-repair（salvage 档）；任何一步成功即进入校验，校验异常文本原样保留进 `validation_error`。
- `feedback_prompt` 输出形如「result.json5 第 X 字段违反 Y 约束，请修正后重新写入」——供子类 `--resume` 回喂。
- 组件不发起模型调用、不含业务规则、不感知后端（四不做边界）。

## 实施步骤

1. pyproject 加依赖；实现三方法与数据类。
2. 单测覆盖宽容格式矩阵与三态。
3. 门禁：`pnpm lint:api`、`pnpm typecheck:api`、`pnpm test:api`、`pnpm verify:flow`。

## 依赖与交付边界

- 依赖：bugfix-15（包骨架与契约）。
- 交付边界：只加 submission.py、依赖与测试；不改子类与业务代码。

## 独立验证

```sh
pnpm test:api -- tests/test_ai_agent_submission.py
```

- 宽容格式矩阵全绿；畸形输入最终落 `invalid` 或 `missing`，绝不抛未捕获异常。

## 验收标准

- 三方法契约与三态终局有测试钉住；JSON5 四类宽容格式各至少一个用例。
- json-repair 兜底仅作回退路径（标准/JSON5 成功时不触发）。
- 反馈文案包含字段名与约束描述。
- CI 全绿。

## 门禁与 CI

- api-static / unit-tests-api / docs-flow。
- 提交与 PR 标题带 `(#N)`。

## 非目标

- 不实现 MCP submit 工具形态。
- 不接 claude-code 子类（bugfix-17）与业务环节。
- 不做 `--json-schema` 快路径。
