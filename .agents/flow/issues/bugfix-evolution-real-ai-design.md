# 自进化真实模型化设计：AI Agent Provider、三层聚类与指令式 Edit patch

[English](bugfix-evolution-real-ai-design.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-14
milestone: bugfix
depends: []
priority: P2
status: ready
scope:
  - plans/fullstack-design/**
  - .agents/**
adr:
  - ../../notes/proposed/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 486
  url: https://github.com/Shadow-Azure/harness-evolution/issues/486
```

## 背景

自进化七步中依赖模型判断的四个环节均为占位实现：聚类是 `lexical-jaccard-v1` 词面 Jaccard（`cluster.py`），case 级置信度固定 0.8（`crud/bad_cases.py`）、簇级为类目常量，严重度是类型常量乘积公式，patch 由 placeholder / minimal-config 两个确定性 source 生成；`docs/architecture.md` 也将「真实评测与 patch」列为未具备。2026-11-22 完成真实模型化的定稿设计（含 Sentry / BERTopic / SkillOpt / Aider 等业界调研与多轮评审：AI Agent Provider 统一封装、三层聚类、自建结构化提交通道、SkillOpt 对齐的指令式 Edit patch），需要把定稿落入 `plans/fullstack-design` 作为后续实现 issue 的唯一设计依据。本 issue 只交付设计文档与决策记录，不实现代码。

## 目标

- `plans/fullstack-design/07-backend-implementation.md` 新增 §5.5.1–§5.5.4 四节：AI Agent Provider 出站适配层、聚类三层（分组 / 审查 / 评分）、结构化提交通道与 JSON 可靠性防线、Edit 指令式 patch。
- `plans/fullstack-design/04-backend-architecture.md` 补目录树 `third_party_api/ai_agent/` 与 §5.1 接缝表「模型出站」行。
- 新增一条 Agent Note 记录关键取舍（三层架构、自建通道 vs `--json-schema`、指令式 vs agent 直改）。
- 设计可回退：后续实现按阶段挂 issue，env 切 fake / placeholder 即回到今天的行为。

## 设计依据

- [07 §5.5.1–§5.5.4](../../../plans/fullstack-design/07-backend-implementation.md)：本 PR 新增的四节即设计本体（Provider 契约与工厂、N 解耦红线与草稿划分完整性、submission 通道与六层防线、EditPlan 数据契约与迭代闭环）。
- [04 §3 分层与目录、§5.1 三类接缝](../../../plans/fullstack-design/04-backend-architecture.md)：ai_agent 出站层的落位，及其与「不再有统一 Provider 层」表述的边界。
- [06 §5.3 聚类固化](../../../plans/fullstack-design/06-database-design.md)：confidence / severity / rank 的存储契约保持不变，三层只换产出方式，零迁移。

## 实现内容

- 07 在 §5.5 与 §5.6 之间插入四节；§5.5 词法聚类原文不动，被引用为分组层第一实现。
- 04 目录树 `third_party_api/` 下加 `ai_agent/` 一行；§5.1 表加「模型出站（自进化）」行，并补一句说明 `ai_agent` 不是早期统一 Provider 的复活。
- Agent Note：`.agents/notes/proposed/feature/2026-11-22-evolution-real-ai-design.md`（三件套），记录四项取舍与被否方案。

## 实施步骤

1. 从 main 切分支 `agent/docs-evolution-real-ai-design`。
2. 修改 04 / 07 两份设计文档。
3. 新增 Agent Note 三件套并 `pnpm record:i18n`。
4. 本地门禁：`pnpm verify:flow`、`pnpm lint:docs`、`pnpm test:gates`。
5. `pnpm flow:sync` 回填 issue 编号。
6. 提交（不含 HTML 工作稿）并开 PR，标题带 `(#N)`。

## 依赖与交付边界

- 依赖：gh 已认证（flow:sync 回填编号）；无代码、数据库、外部服务变更。
- 交付边界：只改 `plans/fullstack-design` 两份文档与 `.agents/`（issue 三件套 + Note 三件套）；`plans/2026-11-22-*` 工作稿（md / HTML）不入 PR。

## 独立验证

```sh
pnpm verify:flow
pnpm lint:docs
pnpm test:gates
grep -c "5.5.1 AI Agent Provider" plans/fullstack-design/07-backend-implementation.md
```

- 四条命令全部通过；grep 输出 1（新节存在且唯一）。

## 验收标准

- 07 含 §5.5.1–§5.5.4、04 含 `ai_agent` 目录行与接缝表行；文档内相对链接有效。
- Agent Note 三件套齐且 i18n hash 配对；PR diff 只含上述文件，不含 HTML。
- CI 全绿。

## 门禁与 CI

- docs-flow lane：doc-sync（`verify:docs`）与 `test:gates`。
- `verify:flow --diff` 校验 PR 标题 `(#N)` 与 scope 覆盖（`plans/fullstack-design/**`、`.agents/**`）。
- 提交与 PR 标题带 `(#N)`。

## 非目标

- 不实现任何代码（`apps/`、`scripts/`、`packages/` 零改动）。
- 不改 API 契约、数据库迁移与前端。
- 不提交 `plans/2026-11-22-*` 工作稿（md / HTML）。
- 不实现向量化分组与 model / opencode 子类（仅设计升级位）。
