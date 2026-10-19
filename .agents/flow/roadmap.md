# 路线图

[English](roadmap.en.md) | 中文

> 愿景与 milestone 序列的唯一事实源。规则契约：[README.md](README.md)。

## 愿景

为 coding agent 建立可观察、可诊断、可验证的进化闭环：先看清真实轨迹，再把问题归因到 harness 层，最后用对照评测决定采纳或回滚。

## Milestone 序列

```yaml flow
kind: roadmap
milestones:
  - m0
  - m1
  - m2
  - m3
```

| 序 | Milestone | 一句话目标 |
|---|---|---|
| m0 | [工程与流程基线](milestones/m0-docs-gates.md) | 脚手架、文档工程、检视与门禁落地 |
| m1 | [轨迹可查看](milestones/m1-trace-viewer.md) | 导入真实 Codex session 并按轮次查看 |
| m2 | [轨迹诊断](milestones/m2-diagnosis.md) | 规则与 AI 诊断，问题回链到证据 |
| m3 | [自进化闭环](milestones/m3-evolution-loop.md) | 从问题到提案、对照评测与采纳 |
