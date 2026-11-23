# AI Agent 三配置项经 GitHub Secrets 注入 .env（缺失即 unset）

[English](bugfix-ai-agent-deploy-injection.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-23
milestone: bugfix
depends:
  - bugfix-15
  - bugfix-17
  - bugfix-21
priority: P2
status: done
scope:
  - deploy/**
  - .github/workflows/deploy.yml
  - docs/deployment.md
  - docs/deployment.en.md
  - docs/deployment.i18n.yaml
  - apps/api/tests/**
  - plans/**
  - .agents/**
  - scripts/doc-budgets.manifest.json
adr:
  - ../../notes/implemented/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 499
  url: https://github.com/Shadow-Azure/harness-evolution/issues/499
```

## 背景

自进化真实模型化的三个运行配置项要生效，生产 .env 必须由部署管道写入：`AI_AGENT_PROVIDER`（bugfix-15，选择 fake / claude-code）、`HE_AI_AGENT_CLAUDE_BIN`（bugfix-17，CLI 路径，默认 `~/.local/bin/claude`）、`HE_PATCH_SOURCE_MODE=agent-edit`（bugfix-21，patch 来源）。要求：三个键经 GitHub Secrets 注入；**Secrets 里没有的键，.env 里也不得存在**——当前 inject-config.py 的语义是「secret 缺失 → 不发键行 → 服务器旧值保留」，这会让删掉的 Secret 残留生效（例如切走 agent-edit 后旧值仍指向它），必须补 unset。

## 目标

- Deploy workflow（`.github/workflows/deploy.yml`）的 .env 注入步骤新增三键：Secret 存在且非空 → `ENTRIES` 追加 `KEY base64(值)`；缺失或空 → `UNSET_ARGS` 追加对应 `--unset KEY`（沿用 HE_GIT_PROXY / HE_GIT_PUSH_TOKEN 的既有条件 unset 模式）。
- 三键与 Secret 同名同义：`AI_AGENT_PROVIDER`、`HE_AI_AGENT_CLAUDE_BIN`、`HE_PATCH_SOURCE_MODE`（该键的合法值经 bugfix-21 扩展 `agent-edit`）。
- `deploy/env.production.example` 增补三键示例与默认值注释（未配置时的回退：`claude-code` / `~/.local/bin/claude` / `placeholder`）。
- `docs/deployment.md` 增补一段：三键的 Secret 名称、语义、缺省回退与「缺失即 unset」的行为。

## 设计依据

- [07 §5.5.1](../../../plans/fullstack-design/07-backend-implementation.md)：三个配置项的定义与默认值。
- `.github/workflows/deploy.yml` 既有模式：ENTRIES 条件追加（CLAUDE_CODE_BASE_URL 可选键先例）与 UNSET_ARGS 条件 unset（HE_GIT_PROXY 先例）；`deploy/inject-config.py` 的原子合并与 `--unset` 语义。
- [docs/deployment.md](../../../docs/deployment.md) 与 [docs/claude-code.md](../../../docs/claude-code.md)：Secret → 服务器配置的既有文档结构。

## 实现内容

- workflow 注入步骤：三个新 Secret 入 env；存在→ENTRIES，缺失→UNSET_ARGS；日志不泄露值（base64 + stdin 既有通道）。
- `env.production.example` 与 `docs/deployment.md` 同步三键。
- 单测（沿 gates.spec / deploy 测试既有形态）：inject 对「三键存在 → 合并写入」「键缺失 → --unset 移除」的行为断言；workflow 的 ENTRIES/UNSET_ARGS 组装逻辑可测则加断言。

## 实施步骤

1. workflow 增三 Secret env 与条件 ENTRIES / UNSET_ARGS。
2. env.production.example 与 docs/deployment.md 增补。
3. 单测与既有 deploy 测试回归。
4. 门禁：`pnpm lint:api`、`pnpm test:gates`、`pnpm verify:flow`。

## 依赖与交付边界

- 依赖：bugfix-15（AI_AGENT_PROVIDER 校验）、bugfix-17（CLAUDE_BIN 消费）、bugfix-21（agent-edit 枚举）。
- 交付边界：只改部署接线、示例与文档、相关测试；不改 Settings 定义与 inject-config.py 的既有原子写语义（--unset 已内建）。

## 独立验证

```sh
pnpm test:gates
pnpm verify:flow
grep -c "AI_AGENT_PROVIDER\|HE_AI_AGENT_CLAUDE_BIN\|HE_PATCH_SOURCE_MODE" deploy/env.production.example
```

- 门禁全绿；grep 输出 ≥3（三键示例齐全）。

## 验收标准

- 三 Secret 全配：服务器 .env 三键为所配值，服务重启后生效（fake / claude-code 可选）。
- 三 Secret 全缺：.env 中三键不存在（unset 移除陈旧值），服务以默认值运行（claude-code / 默认路径 / placeholder）。
- 只配一部分：未配键被 unset、已配键写入，互不影响。
- CI 全绿。

## 门禁与 CI

- api-static / docs-flow（test:gates、verify:docs）/ deploy 相关 lane。
- 提交与 PR 标题带 `(#N)`。

## 非目标

- 不把三键做成 GitHub Variables 或 workflow inputs（保持 Secrets 单一通道）。
- 不改 inject-config.py 的传输与原子写协议。
- 不做 CLAUDE_CODE_* 安装型 Secret 的语义变更（M15 范围）。
- 不增加其余 HE_AI_AGENT_* 键（过度设计裁剪已定，见 #497）。
