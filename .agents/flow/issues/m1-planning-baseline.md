# M1 规划基线与流程树初始化

[English](m1-planning-baseline.en.md) | 中文

```yaml flow
kind: issue
milestone: m1
priority: P0
status: in-progress
scope:
  - .agents/flow/**
  - .agents/notes/proposed/**
  - docs/roadmap.md
  - docs/roadmap.en.md
  - docs/roadmap.i18n.yaml
  - scripts/doc-budgets.manifest.json
adr:
  - ../../notes/proposed/architecture/2026-10-19-session-family-prototype.md
github:
  number: 17
  url: https://github.com/Shadow-Azure/harness-evolution/issues/17
```

## 背景

仓库此前只有流程门禁机制，没有 roadmap、milestone 与 issue 实例。M1 需要先固定产品路线、4 个真实 session family 样本、跨 agent 分析边界与问题到自进化模拟的验收顺序，后续开发才能按 issue 开工。

## 目标

- 初始化 roadmap 与 M1–M4 milestone。
- 建立 M1 的前端原型、agent 流程、统一问题、归因与自进化模拟 issue。
- 记录 session family、稳定锚点与跨 agent 分析决策。

## 验收

- 产品 roadmap 与流程 roadmap 一致，M1–M4 均可机械校验。
- M1 issue 覆盖搜索切换、执行流、统一问题面板、归因与自进化模拟。
- Agent Note 记录 rollout 身份、session family 与跨 agent 分析取舍。
- `verify:flow`、`lint:docs` 与 `verify:docs` 全绿。
- GitHub milestone 与 issue 编号已回填，提交标题可引用编号。
