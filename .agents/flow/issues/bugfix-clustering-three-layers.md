# 聚类三层接入：审查与评分任务、hybrid-lexical-llm-v1 与降级

[English](bugfix-clustering-three-layers.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-19
milestone: bugfix
depends:
  - bugfix-15
  - bugfix-16
priority: P2
status: backlog
scope:
  - apps/api/app/service/evolution/**
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/tests/**
  - .agents/**
adr:
  - ../../notes/proposed/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 493
  url: https://github.com/Shadow-Azure/harness-evolution/issues/493
```

## 背景

设计（#487）把聚类拆为分组（O(N) 无 LLM）/ 审查（O(K×s) 合并命名）/ 评分（O(K×s) 簇置信度 + 严重度）三层，LLM 输入输出与归因报告总量 N 解耦。本 issue 把审查与评分两层接入 prepare 管线；分组层的向量化升级是后续可选项，不在本 issue。

## 目标

- **审查层**：`analyze(task="cluster.review")` 一次调用——输入 = 草稿摘要（约 60 tokens/簇）+ 每草稿采样 3–5 条代表；输出用草稿键引用（`{"from": ["D1","D2"], "title": …}`），只允许合并/命名/摘要；硬闸 = 草稿划分完整性（每个草稿恰出现一次）+ 只合并不拆分，违反整批降级。
- **评分层**：`cluster.score`（簇置信度直评 0–1，rubric 锚定 + `evidence_refs ⊆ 输入` 引用校验）与 `severity.score`（维度 0–10 + CoT grader，overall 为决策分、公式分对照进 metrics、CVSS 式向量串）两次调用、失败隔离。
- 算法标识升级 `hybrid-lexical-llm-v1` 随 run 快照落库；簇 title/description/confidence/severity 用 LLM 产物。
- 降级矩阵：审查失败 → 草稿直用；`cluster.score` 失败 → 类目常量；`severity.score` 失败 → `cluster_severity()` 公式；均记 `degraded` 事件。

## 设计依据

- [07 §5.5.2](../../../plans/fullstack-design/07-backend-implementation.md)：三层定义、N 解耦红线（草稿键引用 + 代表采样 + 统计量注入）、两评分任务与降级矩阵。
- [06 §5.3](../../../plans/fullstack-design/06-database-design.md)：confidence/severity/rank 存储契约不变，零迁移。

## 实现内容

- service 层新增任务模型与语义 validator（划分完整性、引用子集、键集合一致）；prompt 模板与采样上界常量。
- prepare 管线在词面草稿后插入两次调用（fake provider 下全链路可测）。
- run events 记 `ai_agent_call`（task/model/tokens/cost/latency/outcome）与 `degraded`。

## 实施步骤

1. 任务模型 + validator + 单测（fake）。
2. prepare 接线与降级路径测试。
3. 回归既有聚类/七步测试（词面路径行为不变）。
4. 门禁：`pnpm lint:api`、`pnpm typecheck:api`、`pnpm test:api`、`pnpm verify:flow`。

## 依赖与交付边界

- 依赖：bugfix-15（provider 骨架）、bugfix-16（submission 收货）；真实 claude-code（bugfix-17）非必需——验收以 fake 达成。
- 交付边界：只改聚类相关的 service 编排与任务模型；不改 DB 表与 API 契约；不做 embedding 分组。

## 独立验证

```sh
pnpm test:api -- tests/test_clustering_three_layers.py
```

- 划分完整性（缺草稿/重复引用被拒）、引用子集校验、三条降级路径全部有断言。

## 验收标准

- cluster-only run（fake）端到端：草稿 → 审查合并 → 评分落库，算法标识为 `hybrid-lexical-llm-v1`。
- 三条降级路径各自独立触发且不阻塞 run；最坏情况等于今天的行为。
- LLM 输入规模随簇数与采样数而非 N（有采样上界常量与测试）。
- CI 全绿。

## 门禁与 CI

- api-static / unit-tests-api / docs-flow。
- 提交与 PR 标题带 `(#N)`。

## 非目标

- 不做向量化分组与 `SupportsEmbedding`（后续可选 issue）。
- 不改 patch 生成（bugfix-20/21）。
- 不做逐 case 模型置信度。
