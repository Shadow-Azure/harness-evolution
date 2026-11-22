# AI 调用观测事件完善与常驻文档收尾

[English](bugfix-ai-agent-observability-docs.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-22
milestone: bugfix
depends:
  - bugfix-19
  - bugfix-21
priority: P2
status: backlog
scope:
  - apps/api/**
  - docs/**
  - .agents/**
adr:
  - ../../notes/proposed/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 489
  url: https://github.com/Shadow-Azure/harness-evolution/issues/489
```

## 背景

实施链（bugfix-15→21）落地后收尾：把 `ai_agent_call` 观测事件补全为可运营指标，更新常驻文档（architecture/development/新 ai-agent 页），并把设计 Note 从 proposed 转 implemented。

## 目标

- **观测**：`ai_agent_call` 事件统一记录 task、provider、model、tokens、cost、latency、outcome（含 `degraded` 与回喂重试次数）；提交文件解析失败率可从事件序列统计。
- **文档**：`docs/` 新增 ai-agent 出站层页（中英成对，登记词数预算）；`docs/architecture.md` 的「未具备」清单按实际交付更新（真实 patch 落地、真实评测仍按 eval 网关现状表述）；`docs/development.md` 增补配置说明——仅 `AI_AGENT_PROVIDER`、`HE_AI_AGENT_CLAUDE_BIN`（带默认）与 `HE_PATCH_SOURCE_MODE` 的 `agent-edit` 枚举值。
- **Note**：`proposed/feature/2026-11-22-evolution-real-ai-design.md` 随实际落地更新事实并转 `implemented/`（或按落地范围部分转，语义由维护者判断）。
- AGENTS.md 命令清单无新增（无新脚本命令）。

## 设计依据

- [07 §5.5.1–§5.5.3](../../../plans/fullstack-design/07-backend-implementation.md)：观测字段与六层防线的第 5 层。
- [docs/AGENTS.md](../../../docs/AGENTS.md)：常驻文档层级、双语成对与词数预算规则。
- [.agents/notes/README.md](../../notes/README.md)：Note 随落地保持同步的 lifecycle 规则。

## 实现内容

- 事件字段核对与补齐（如缺）；一处统计辅助或查询示例（可选）。
- 三份文档改动 + `pnpm record:i18n` + 词数预算登记。
- Note 状态迁移与事实同步。

## 实施步骤

1. 核对事件字段覆盖，补缺口。
2. 文档三处 + 预算 + i18n。
3. Note 迁移。
4. 门禁：`pnpm lint:docs`、`pnpm verify:docs`、`pnpm verify:flow`、`pnpm test:api`。

## 依赖与交付边界

- 依赖：bugfix-19（聚类接入）、bugfix-21（patch 闭环）——观测与文档描述它们的最终形态。
- 交付边界：观测事件与文档/Note；不改业务行为。

## 独立验证

```sh
pnpm lint:docs && pnpm verify:docs
```

- 双语配对、预算登记、死链检查全绿；事件字段在测试中有断言。

## 验收标准

- 每个 AI 调用在 run events 可见完整字段；降级与重试可追溯。
- 新文档页中英成对且登记预算；architecture「未具备」表述与现状一致。
- Note 状态与事实同步。
- CI 全绿。

## 门禁与 CI

- docs-flow（doc-sync）/ api-static / unit-tests-api。
- 提交与 PR 标题带 `(#N)`。

## 非目标

- 不做前端观测面板。
- 不新增监控告警集成。
- 不改 Provider 接口。
